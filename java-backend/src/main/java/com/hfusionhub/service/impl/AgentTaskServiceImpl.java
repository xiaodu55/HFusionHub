package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.AgentRunDTO;
import com.hfusionhub.dto.AgentStepDTO;
import com.hfusionhub.dto.AgentTaskDetailDTO;
import com.hfusionhub.dto.AgentTaskSummaryDTO;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentStep;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.service.AgentTaskService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Agent 任务状态机服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentTaskServiceImpl implements AgentTaskService {

    private final AgentTaskMapper taskMapper;
    private final AgentRunMapper runMapper;
    private final AgentStepMapper stepMapper;

    // ================================================================
    // 生命周期方法
    // ================================================================

    @Override
    @Transactional
    public AgentTask createTask(String requestId, Long userId, Long conversationId,
                                Long kbId, String query) {
        // 幂等：相同 requestId 返回已有任务
        AgentTask existing = taskMapper.selectByRequestId(requestId);
        if (existing != null) {
            log.debug("Agent task already exists for requestId: {}", requestId);
            return existing;
        }

        AgentTask task = new AgentTask();
        task.setRequestId(requestId);
        task.setUserId(userId);
        task.setConversationId(conversationId);
        task.setKnowledgeBaseId(kbId);
        task.setQuery(query);
        task.setStatus(AgentConstants.STATUS_PENDING);
        taskMapper.insert(task);
        log.info("Created agent task id={} requestId={}", task.getId(), requestId);
        return task;
    }

    @Override
    @Transactional
    public AgentRun startRun(Long taskId, String runUuid, String model,
                             String style, int maxToolSteps) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new BusinessException("Agent任务不存在: " + taskId);
        }

        // 校验状态转移：pending → running
        if (!AgentConstants.canTransition(task.getStatus(), AgentConstants.STATUS_RUNNING)) {
            throw new BusinessException(String.format(
                    "无法启动运行：任务状态 %s 不允许转移为 %s",
                    task.getStatus(), AgentConstants.STATUS_RUNNING));
        }

        // 计算尝试次数
        List<AgentRun> existingRuns = runMapper.selectByTaskId(taskId);
        int attemptNumber = existingRuns.size() + 1;

        AgentRun run = new AgentRun();
        run.setTaskId(taskId);
        run.setRunUuid(runUuid);
        run.setAttemptNumber(attemptNumber);
        run.setStatus(AgentConstants.STATUS_RUNNING);
        run.setModel(model);
        run.setStyle(style != null ? style : "detailed");
        run.setMaxToolSteps(maxToolSteps > 0 ? maxToolSteps : 5);
        run.setStartedAt(LocalDateTime.now());
        runMapper.insert(run);

        // 更新 task 状态为 running，记录当前 run
        task.setStatus(AgentConstants.STATUS_RUNNING);
        task.setCurrentRunId(run.getId());
        taskMapper.updateById(task);

        log.info("Started agent run id={} uuid={} attempt={} for task={}",
                run.getId(), runUuid, attemptNumber, taskId);
        return run;
    }

    @Override
    @Transactional
    public void recordStep(Long runId, int sequence, String stepType, String action,
                           String inputSummary, String outputSummary,
                           List<Map<String, Object>> sources, long durationMs,
                           String errorCode) {
        // 幂等：相同 (runId, sequence) 不重复插入
        AgentStep existing = stepMapper.selectOne(
                new LambdaQueryWrapper<AgentStep>()
                        .eq(AgentStep::getRunId, runId)
                        .eq(AgentStep::getSequence, sequence));
        if (existing != null) {
            log.debug("Step {} already exists for run {}", sequence, runId);
            return;
        }

        AgentStep step = new AgentStep();
        step.setRunId(runId);
        step.setSequence(sequence);
        step.setStepType(stepType);
        step.setAction(action);
        step.setInputSummary(truncate(inputSummary, AgentConstants.INPUT_SUMMARY_MAX_LENGTH));
        step.setOutputSummary(truncate(outputSummary, AgentConstants.OUTPUT_SUMMARY_MAX_LENGTH));
        step.setSources(sources);
        step.setDurationMs(durationMs);
        step.setErrorCode(errorCode);
        stepMapper.insert(step);
    }

    @Override
    @Transactional
    public void completeRun(Long runId, String status, String model,
                            Map<String, Object> tokenUsage, int toolCallsCount,
                            long durationMs, String errorCode, String errorDetail,
                            String failedTool) {
        // 终态白名单校验：拒绝未定义的状态写入 Task/Run
        if (!AgentConstants.isValidTerminalStatus(status)) {
            log.error("Rejected invalid terminal status '{}' for run {} — falling back to failed", status, runId);
            errorCode = (errorCode != null) ? errorCode : AgentConstants.ERR_INTERNAL_ERROR;
            errorDetail = (errorDetail != null) ? errorDetail : ("Illegal status received: " + status);
            status = AgentConstants.STATUS_FAILED;
        }

        AgentRun run = runMapper.selectById(runId);
        if (run == null) {
            log.warn("Agent run not found for completion: {}", runId);
            return;
        }

        // 计算实际耗时
        long actualDuration = durationMs;
        if (actualDuration <= 0 && run.getStartedAt() != null) {
            actualDuration = java.time.Duration.between(
                    run.getStartedAt(), LocalDateTime.now()).toMillis();
        }

        run.setStatus(status);
        if (model != null) run.setModel(model);
        if (tokenUsage != null) run.setTokenUsage(tokenUsage);
        run.setToolCallsCount(toolCallsCount);
        run.setDurationMs(actualDuration);
        run.setErrorCode(errorCode);
        run.setErrorDetail(errorDetail);
        run.setFailedTool(failedTool);
        run.setCompletedAt(LocalDateTime.now());
        runMapper.updateById(run);

        // 同步更新 task 状态
        AgentTask task = taskMapper.selectById(run.getTaskId());
        if (task != null) {
            task.setStatus(status);
            taskMapper.updateById(task);
        }

        log.info("Agent run {} completed: status={} duration={}ms toolCalls={}",
                runId, status, actualDuration, toolCallsCount);
    }

    @Override
    @Transactional
    public void failRun(Long runId, String errorCode, String errorDetail, String failedTool) {
        completeRun(runId, AgentConstants.STATUS_FAILED, null, null, 0, 0,
                errorCode, errorDetail, failedTool);
    }

    @Override
    @Transactional
    public void cancelRun(Long runId) {
        completeRun(runId, AgentConstants.STATUS_CANCELLED, null, null, 0, 0,
                AgentConstants.ERR_CANCELLED, "用户取消", null);
    }

    // ================================================================
    // 查询方法
    // ================================================================

    @Override
    public AgentTaskDetailDTO getTaskDetail(Long taskId) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) return null;
        return buildDetail(task);
    }

    @Override
    public AgentTaskDetailDTO getTaskByRequestId(String requestId) {
        AgentTask task = taskMapper.selectByRequestId(requestId);
        if (task == null) return null;
        return buildDetail(task);
    }

    @Override
    public PageResult<AgentTaskSummaryDTO> listUserTasks(Long userId, String status,
                                                         int page, int pageSize) {
        int offset = (page - 1) * pageSize;
        List<AgentTask> tasks = taskMapper.selectByUserIdAndStatus(
                userId, status, offset, pageSize);
        int total = taskMapper.countByUserIdAndStatus(userId, status);

        List<AgentTaskSummaryDTO> summaries = tasks.stream()
                .map(this::buildSummary)
                .collect(Collectors.toList());

        PageResult<AgentTaskSummaryDTO> result = PageResult.of(page, pageSize, total, summaries);
        return result;
    }

    @Override
    public List<AgentRun> getRunsByTaskId(Long taskId) {
        return runMapper.selectByTaskId(taskId);
    }

    // ================================================================
    // 操作方法
    // ================================================================

    @Override
    @Transactional
    public AgentRun retryTask(Long taskId, Long userId) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new BusinessException("任务不存在: " + taskId);
        }
        if (!task.getUserId().equals(userId)) {
            throw new BusinessException("无权操作此任务");
        }
        if (!AgentConstants.RETRYABLE_STATUSES.contains(task.getStatus())) {
            throw new BusinessException("只能重试失败或超时的任务，当前状态: " + task.getStatus());
        }

        // 重置 task 为 pending
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(null);
        taskMapper.updateById(task);

        log.info("Task {} reset to pending for retry by user {}", taskId, userId);
        // 实际的重新执行由调用方（Controller 或前端）触发
        return null;
    }

    @Override
    public boolean cancelTask(Long taskId, Long userId) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new BusinessException("任务不存在: " + taskId);
        }
        if (!task.getUserId().equals(userId)) {
            throw new BusinessException("无权操作此任务");
        }
        if (!AgentConstants.STATUS_RUNNING.equals(task.getStatus())) {
            return false;
        }

        // 标记 task 和 current run 为 cancelled
        if (task.getCurrentRunId() != null) {
            cancelRun(task.getCurrentRunId());
        }
        task.setStatus(AgentConstants.STATUS_CANCELLED);
        taskMapper.updateById(task);

        log.info("Task {} cancelled by user {}", taskId, userId);
        return true;
    }

    // ================================================================
    // 内部辅助方法
    // ================================================================

    private AgentTaskDetailDTO buildDetail(AgentTask task) {
        List<AgentRun> runs = runMapper.selectByTaskId(task.getId());

        List<AgentRunDTO> runDTOs = runs.stream().map(run -> {
            List<AgentStep> steps = stepMapper.selectByRunId(run.getId());
            List<AgentStepDTO> stepDTOs = steps.stream().map(step ->
                    AgentStepDTO.builder()
                            .id(step.getId())
                            .runId(step.getRunId())
                            .sequence(step.getSequence())
                            .stepType(step.getStepType())
                            .action(step.getAction())
                            .inputSummary(step.getInputSummary())
                            .outputSummary(step.getOutputSummary())
                            .sources(step.getSources())
                            .durationMs(step.getDurationMs())
                            .errorCode(step.getErrorCode())
                            .createdAt(step.getCreatedAt())
                            .build()
            ).collect(Collectors.toList());

            return AgentRunDTO.builder()
                    .id(run.getId())
                    .taskId(run.getTaskId())
                    .runUuid(run.getRunUuid())
                    .attemptNumber(run.getAttemptNumber())
                    .status(run.getStatus())
                    .model(run.getModel())
                    .style(run.getStyle())
                    .maxToolSteps(run.getMaxToolSteps())
                    .tokenUsage(run.getTokenUsage())
                    .toolCallsCount(run.getToolCallsCount())
                    .errorCode(run.getErrorCode())
                    .errorDetail(run.getErrorDetail())
                    .failedTool(run.getFailedTool())
                    .startedAt(run.getStartedAt())
                    .completedAt(run.getCompletedAt())
                    .durationMs(run.getDurationMs())
                    .createdAt(run.getCreatedAt())
                    .steps(stepDTOs)
                    .build();
        }).collect(Collectors.toList());

        return AgentTaskDetailDTO.builder()
                .id(task.getId())
                .requestId(task.getRequestId())
                .userId(task.getUserId())
                .conversationId(task.getConversationId())
                .knowledgeBaseId(task.getKnowledgeBaseId())
                .query(task.getQuery())
                .status(task.getStatus())
                .currentRunId(task.getCurrentRunId())
                .createdAt(task.getCreatedAt())
                .updatedAt(task.getUpdatedAt())
                .runs(runDTOs)
                .build();
    }

    private AgentTaskSummaryDTO buildSummary(AgentTask task) {
        List<AgentRun> runs = runMapper.selectByTaskId(task.getId());

        String lastErrorCode = null;
        String lastErrorMessage = null;
        long totalDuration = 0;
        for (AgentRun run : runs) {
            if (run.getDurationMs() != null) {
                totalDuration += run.getDurationMs();
            }
            if (run.getErrorCode() != null) {
                lastErrorCode = run.getErrorCode();
                lastErrorMessage = run.getErrorDetail();
            }
        }

        String querySummary = task.getQuery();
        if (querySummary != null && querySummary.length() > AgentConstants.QUERY_SUMMARY_MAX_LENGTH) {
            querySummary = querySummary.substring(0, AgentConstants.QUERY_SUMMARY_MAX_LENGTH) + "...";
        }

        return AgentTaskSummaryDTO.builder()
                .id(task.getId())
                .requestId(task.getRequestId())
                .query(querySummary)
                .knowledgeBaseId(task.getKnowledgeBaseId())
                .status(task.getStatus())
                .runCount(runs.size())
                .lastErrorCode(lastErrorCode)
                .lastErrorMessage(lastErrorMessage)
                .totalDurationMs(totalDuration)
                .createdAt(task.getCreatedAt())
                .updatedAt(task.getUpdatedAt())
                .build();
    }

    private static String truncate(String text, int maxLen) {
        if (text == null) return null;
        if (text.length() <= maxLen) return text;
        return text.substring(0, maxLen - 3) + "...";
    }
}
