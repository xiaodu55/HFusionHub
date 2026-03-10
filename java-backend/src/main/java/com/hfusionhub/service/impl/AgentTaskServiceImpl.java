package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.AgentRunDTO;
import com.hfusionhub.dto.AgentStepDTO;
import com.hfusionhub.dto.AgentTaskDetailDTO;
import com.hfusionhub.dto.AgentTaskSummaryDTO;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentStep;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.mapper.AgentApprovalMapper;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.entity.Message;
import com.hfusionhub.service.AgentTaskService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
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
    private final AgentApprovalMapper approvalMapper;
    private final MessageMapper messageMapper;
    private final AiClient aiClient;

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

    @Override
    public AgentRun getRunById(Long runId) {
        return runMapper.selectById(runId);
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
    // Agent V1 Step 5: 审批方法
    // ================================================================

    @Override
    @Transactional
    public AgentApproval pauseForApproval(Long taskId, Long runId, Long userId,
                                          String toolName, String toolInput,
                                          String argumentsSummary) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) throw new BusinessException("任务不存在: " + taskId);

        // 状态转移: running → waiting_approval
        if (!AgentConstants.canTransition(task.getStatus(), AgentConstants.STATUS_WAITING_APPROVAL)) {
            throw new BusinessException("当前状态不允许转入等待审批: " + task.getStatus());
        }

        // 计算参数哈希（审批令牌绑定）
        String toolInputHash = sha256(taskId + ":" + runId + ":" + userId + ":" + toolName + ":" + toolInput);

        AgentApproval approval = new AgentApproval();
        approval.setApprovalId(java.util.UUID.randomUUID().toString());
        approval.setTaskId(taskId);
        approval.setRunId(runId);
        approval.setUserId(userId);
        approval.setToolName(toolName);
        approval.setToolInputHash(toolInputHash);
        approval.setArgumentsSummary(argumentsSummary);
        approval.setStatus("pending");
        approval.setExpiresAt(java.time.LocalDateTime.now().plusMinutes(5));
        approvalMapper.insert(approval);

        // 更新 task 状态
        task.setStatus(AgentConstants.STATUS_WAITING_APPROVAL);
        taskMapper.updateById(task);

        // 更新 run 状态
        AgentRun run = runMapper.selectById(runId);
        if (run != null) {
            run.setStatus(AgentConstants.STATUS_WAITING_APPROVAL);
            runMapper.updateById(run);
        }

        log.info("Task {} paused for approval: approvalId={} tool={}", taskId,
                approval.getApprovalId(), toolName);
        return approval;
    }

    @Override
    public AgentApproval decideApproval(String approvalId, String decision,
                                         Long decidedBy, String reason) {
        AgentApproval approval = approvalMapper.selectByApprovalId(approvalId);
        if (approval == null) throw new BusinessException("审批记录不存在: " + approvalId);
        if (!"pending".equals(approval.getStatus()))
            throw new BusinessException("审批状态不允许决定: " + approval.getStatus());
        if (approval.getExpiresAt().isBefore(java.time.LocalDateTime.now()))
            throw new BusinessException("审批已过期");

        // ── Phase 1: MySQL updates (auto-committed per statement) ──
        String newStatus = "approved".equals(decision) ? "approved" : "denied";
        approvalMapper.updateDecision(approval.getId(), newStatus, decidedBy,
                LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")), reason);

        AgentTask task = taskMapper.selectById(approval.getTaskId());
        AgentRun run = runMapper.selectById(approval.getRunId());

        if ("denied".equals(decision)) {
            if (task != null) {
                task.setStatus(AgentConstants.STATUS_FAILED);
                taskMapper.updateById(task);
            }
            if (run != null) {
                run.setStatus(AgentConstants.STATUS_FAILED);
                run.setErrorCode("approval_denied");
                run.setErrorDetail("审批被拒绝: " + (reason != null ? reason : "无理由"));
                run.setCompletedAt(java.time.LocalDateTime.now());
                runMapper.updateById(run);
            }
            log.info("Approval {} DENIED by user {}: tool={} reason={}",
                    approvalId, decidedBy, approval.getToolName(), reason);
        } else {
            if (task != null && AgentConstants.canTransition(task.getStatus(), AgentConstants.STATUS_RUNNING)) {
                task.setStatus(AgentConstants.STATUS_RUNNING);
                taskMapper.updateById(task);
            }
            if (run != null) {
                run.setStatus(AgentConstants.STATUS_RUNNING);
                runMapper.updateById(run);
            }
            log.info("Approval {} APPROVED by user {}: tool={} (will call Python resume)",
                    approvalId, decidedBy, approval.getToolName());
        }

        approval.setStatus(newStatus);
        approval.setDecidedBy(decidedBy);
        approval.setReason(reason);

        // ── Phase 2: Call Python (outside any transaction — recordStep
        //        and completeRun manage their own transactions). ──
        if ("approved".equals(decision) && task != null && run != null) {
            try {
                resumeAgentAfterApproval(approval, task, run);
            } catch (Exception e) {
                String errorMsg = e.getClass().getSimpleName() + ": "
                        + (e.getMessage() != null ? e.getMessage() : "(null message)");
                log.error("Failed to resume agent after approval {}: {}",
                        approvalId, errorMsg, e);
                // Converge run and task to failed so nothing is stuck
                // in 'running' after a failed Python resume call.
                try {
                    AgentRun checkRun = runMapper.selectById(run.getId());
                    if (checkRun != null) {
                        String currentStatus = checkRun.getStatus();
                        if (!AgentConstants.TERMINAL_STATUSES.contains(currentStatus)) {
                            checkRun.setStatus(AgentConstants.STATUS_FAILED);
                            checkRun.setErrorCode("internal_error");
                            checkRun.setErrorDetail("审批后恢复执行失败: " + errorMsg);
                            checkRun.setCompletedAt(LocalDateTime.now());
                            runMapper.updateById(checkRun);
                            AgentTask checkTask = taskMapper.selectById(
                                    checkRun.getTaskId());
                            if (checkTask != null && !AgentConstants.TERMINAL_STATUSES.contains(
                                    checkTask.getStatus())) {
                                checkTask.setStatus(AgentConstants.STATUS_FAILED);
                                taskMapper.updateById(checkTask);
                            }
                        }
                    } else {
                        // Even if the run can't be found now, update the
                        // in-memory run reference to failed and persist it.
                        log.warn("Could not re-read run {} after resume failure — updating original reference", run.getId());
                        run.setStatus(AgentConstants.STATUS_FAILED);
                        run.setErrorCode("internal_error");
                        run.setErrorDetail("审批后恢复执行失败: " + errorMsg);
                        run.setCompletedAt(LocalDateTime.now());
                        runMapper.updateById(run);
                        if (task != null && !AgentConstants.TERMINAL_STATUSES.contains(task.getStatus())) {
                            task.setStatus(AgentConstants.STATUS_FAILED);
                            taskMapper.updateById(task);
                        }
                    }
                } catch (Exception convergenceError) {
                    log.error("CRITICAL: Failed to converge run/task to failed after approval error. "
                            + "Run {} may be stuck in non-terminal state. Error: {}",
                            run.getId(), convergenceError.getMessage(), convergenceError);
                }
            }
        }

        return approval;
    }

    /**
     * Call Python /api/agent/v1/chat/decide to execute the approved tool
     * and complete the agent run.  Runs OUTSIDE the @Transactional boundary
     * so that the MySQL approval update is committed before the (potentially
     * slow) tool execution.
     */
    private void resumeAgentAfterApproval(AgentApproval approval, AgentTask task, AgentRun run) {
        Long runId = run.getId();
        // Build chat history from messages
        List<Map<String, String>> history = List.of();
        Long conversationId = task.getConversationId();
        if (conversationId != null) {
            history = getChatHistoryForTask(conversationId);
        }

        // Parse tool input from arguments summary
        String toolInput = "{}";
        if (approval.getArgumentsSummary() != null && !approval.getArgumentsSummary().isBlank()) {
            toolInput = approval.getArgumentsSummary();
        }

        // Call Python to execute the approved tool and continue the agent loop
        AiClient.ChatResponse aiResponse = aiClient.decideApproval(
                approval.getApprovalId(),
                "approved",
                approval.getReason(),
                approval.getUserId(),
                task.getKnowledgeBaseId(),
                approval.getToolName(),
                toolInput,
                task.getQuery(),
                history,
                conversationId,
                run.getModel()
        );

        // Record step events from the resumed run
        if (aiResponse.getStepEvents() != null) {
            int seq = stepMapper.countByRunId(runId);
            for (Map<String, Object> stepEvent : aiResponse.getStepEvents()) {
                if (stepEvent == null) continue;
                seq++;
                String stepType = stepEvent.get("step_type") != null
                        ? stepEvent.get("step_type").toString() : "tool_call";
                String action = stepEvent.get("action") != null
                        ? stepEvent.get("action").toString() : null;
                String inputSummary = stepEvent.get("input_summary") != null
                        ? stepEvent.get("input_summary").toString() : null;
                String outputSummary = stepEvent.get("output_summary") != null
                        ? stepEvent.get("output_summary").toString() : null;
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> sources = stepEvent.get("sources") instanceof List
                        ? (List<Map<String, Object>>) stepEvent.get("sources") : null;
                long durationMs = stepEvent.get("duration_ms") instanceof Number n
                        ? n.longValue() : 0L;
                String errorCode = stepEvent.get("error_code") != null
                        ? stepEvent.get("error_code").toString() : null;

                recordStep(runId, seq, stepType, action,
                        inputSummary, outputSummary, sources, durationMs, errorCode);
            }
        }

        // Complete the run based on Python response
        String pythonStatus = aiResponse.getStatus();
        if (pythonStatus == null) pythonStatus = "completed";
        String mappedStatus = AgentConstants.mapPythonStatus(pythonStatus);

        Map<String, Object> tokenUsage = null;
        if (aiResponse.getTokenUsage() != null) {
            Map<String, Object> usage = aiResponse.getTokenUsage();
            tokenUsage = Map.of(
                "prompt_tokens", usage.getOrDefault("prompt_tokens", 0),
                "completion_tokens", usage.getOrDefault("completion_tokens", 0),
                "total_tokens", usage.getOrDefault("total_tokens", 0));
        }

        // Update the run and task directly.
        // The Python call may have taken several seconds, so HikariCP
        // connections may have been recycled.  Use a fresh lookup with
        // a single retry on MyBatisSystemException.
        // If the fresh lookup fails, fall back to the original reference
        // so the run NEVER stays non-terminal.
        AgentRun freshRun = null;
        for (int retry = 0; retry < 2 && freshRun == null; retry++) {
            try {
                freshRun = runMapper.selectById(runId);
            } catch (Exception selectEx) {
                if (retry == 0) {
                    log.warn("runMapper.selectById({}) failed on attempt {}: {} — retrying",
                            runId, retry + 1, selectEx.getMessage());
                    try { Thread.sleep(200); } catch (InterruptedException ignored) {}
                } else {
                    log.error("runMapper.selectById({}) failed on final attempt — falling back to original reference", runId);
                }
            }
        }
        if (freshRun == null) {
            log.warn("Could not re-read run {} after Python resume — updating original entity reference", runId);
            freshRun = run;
        }

        long actualDuration = 0L;
        if (freshRun.getStartedAt() != null) {
            actualDuration = java.time.Duration.between(
                    freshRun.getStartedAt(), LocalDateTime.now()).toMillis();
        }
        freshRun.setStatus(mappedStatus);
        if (tokenUsage != null) freshRun.setTokenUsage(tokenUsage);
        freshRun.setToolCallsCount(aiResponse.getToolCallsCount());
        freshRun.setDurationMs(actualDuration);
        freshRun.setCompletedAt(LocalDateTime.now());
        runMapper.updateById(freshRun);

        AgentTask freshTask = taskMapper.selectById(freshRun.getTaskId());
        if (freshTask != null) {
            freshTask.setStatus(mappedStatus);
            taskMapper.updateById(freshTask);
        } else {
            // Fallback: update the original task reference
            task.setStatus(mappedStatus);
            taskMapper.updateById(task);
        }

        String contentPreview = "";
        if (aiResponse.getContent() != null && aiResponse.getContent().length() > 0) {
            contentPreview = aiResponse.getContent().substring(0,
                    Math.min(100, aiResponse.getContent().length()));
        }
        log.info("Agent run {} resumed after approval {}: status={} answer={}",
                runId, approval.getApprovalId(), mappedStatus, contentPreview);
    }

    /**
     * Get recent chat history for a conversation.
     */
    private List<Map<String, String>> getChatHistoryForTask(Long conversationId) {
        if (conversationId == null) return List.of();
        try {
            LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
            wrapper.eq(Message::getConversationId, conversationId)
                    .orderByDesc(Message::getCreatedAt)
                    .last("LIMIT 20");
            List<Message> messages = messageMapper.selectList(wrapper);
            java.util.Collections.reverse(messages);
            return messages.stream()
                    .filter(m -> m.getContent() != null && !m.getContent().isBlank())
                    .map(m -> {
                        Map<String, String> map = new HashMap<>();
                        map.put("role", m.getRole());
                        map.put("content", m.getContent());
                        return map;
                    })
                    .collect(Collectors.toList());
        } catch (Exception e) {
            log.warn("Failed to get chat history for conversation {}: {}",
                    conversationId, e.getMessage());
            return List.of();
        }
    }

    @Override
    public AgentApproval getApproval(String approvalId) {
        return approvalMapper.selectByApprovalId(approvalId);
    }

    @Override
    public List<AgentApproval> listPendingApprovals(Long userId) {
        return approvalMapper.selectPendingByUserId(userId);
    }

    @Override
    public List<AgentApproval> getApprovalsByTaskId(Long taskId) {
        return approvalMapper.selectByTaskId(taskId);
    }

    @Override
    @Transactional
    public int expireApprovals() {
        String nowStr = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        List<AgentApproval> expired = approvalMapper.selectExpiredPending(nowStr);
        for (AgentApproval a : expired) {
            approvalMapper.updateDecision(a.getId(), "expired", null,
                    nowStr, "审批超时自动拒绝");
            // 更新 task → failed
            AgentTask task = taskMapper.selectById(a.getTaskId());
            if (task != null && AgentConstants.STATUS_WAITING_APPROVAL.equals(task.getStatus())) {
                task.setStatus(AgentConstants.STATUS_FAILED);
                taskMapper.updateById(task);
            }
            AgentRun run = runMapper.selectById(a.getRunId());
            if (run != null) {
                run.setStatus(AgentConstants.STATUS_FAILED);
                run.setErrorCode("approval_expired");
                run.setErrorDetail("审批超时（5分钟未响应）");
                run.setCompletedAt(java.time.LocalDateTime.now());
                runMapper.updateById(run);
            }
        }
        if (!expired.isEmpty()) {
            log.info("Expired {} pending approvals", expired.size());
        }
        return expired.size();
    }

    private static String sha256(String input) {
        try {
            java.security.MessageDigest md = java.security.MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest(input.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : hash) hex.append(String.format("%02x", b));
            return hex.toString();
        } catch (Exception e) {
            return input; // fallback — should never happen
        }
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
