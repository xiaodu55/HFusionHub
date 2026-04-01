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
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.entity.Message;
import com.hfusionhub.service.AgentTaskService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Lazy;
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
public class AgentTaskServiceImpl implements AgentTaskService {

    private final AgentTaskMapper taskMapper;
    private final AgentRunMapper runMapper;
    private final AgentStepMapper stepMapper;
    private final AgentApprovalMapper approvalMapper;
    private final MessageMapper messageMapper;
    private final UserMapper userMapper;
    private final AiClient aiClient;
    private final com.hfusionhub.service.AgentTaskQueueService queueService;
    private final com.hfusionhub.service.AgentStatusEventService statusEventService;
    private final com.hfusionhub.common.utils.RedisUtils redisUtils;

    @SuppressWarnings("java:S107")
    public AgentTaskServiceImpl(
            AgentTaskMapper taskMapper,
            AgentRunMapper runMapper,
            AgentStepMapper stepMapper,
            AgentApprovalMapper approvalMapper,
            MessageMapper messageMapper,
            UserMapper userMapper,
            AiClient aiClient,
            @Lazy com.hfusionhub.service.AgentTaskQueueService queueService,
            com.hfusionhub.service.AgentStatusEventService statusEventService,
            com.hfusionhub.common.utils.RedisUtils redisUtils) {
        this.taskMapper = taskMapper;
        this.runMapper = runMapper;
        this.stepMapper = stepMapper;
        this.approvalMapper = approvalMapper;
        this.messageMapper = messageMapper;
        this.userMapper = userMapper;
        this.aiClient = aiClient;
        this.queueService = queueService;
        this.statusEventService = statusEventService;
        this.redisUtils = redisUtils;
    }
    @org.springframework.beans.factory.annotation.Value("${agent.run.lease-seconds:120}")
    private int leaseSeconds;
    @org.springframework.beans.factory.annotation.Value("${agent.cancel-flag-ttl-seconds:3600}")
    private int cancelFlagTtlSeconds;

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
        return startRun(taskId, runUuid, model, style, maxToolSteps, null);
    }

    @Override
    @Transactional
    public AgentRun startRun(Long taskId, String runUuid, String model,
                             String style, int maxToolSteps, String leaseHolder) {
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

        LocalDateTime now = LocalDateTime.now();
        AgentRun run = new AgentRun();
        run.setTaskId(taskId);
        run.setRunUuid(runUuid);
        run.setAttemptNumber(attemptNumber);
        run.setStatus(AgentConstants.STATUS_RUNNING);
        run.setModel(model);
        run.setStyle(style != null ? style : "detailed");
        run.setMaxToolSteps(maxToolSteps > 0 ? maxToolSteps : 5);
        run.setStartedAt(now);
        run.setDispatchCount(1);
        // V13: lease support — stream path passes "stream:...", worker passes worker ID
        if (leaseHolder != null) {
            run.setLeaseHolder(leaseHolder);
            run.setLeaseExpiresAt(now.plusSeconds(leaseSeconds));
            run.setHeartbeatAt(now);
        }
        runMapper.insert(run);

        // 更新 task 状态为 running，记录当前 run
        task.setStatus(AgentConstants.STATUS_RUNNING);
        task.setCurrentRunId(run.getId());
        taskMapper.updateById(task);

        log.info("Started agent run id={} uuid={} attempt={} for task={} leaseHolder={}",
                run.getId(), runUuid, attemptNumber, taskId, leaseHolder);
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

        // V13: 守护终态写入 — 仅 running/waiting_approval → 终态
        int affected = runMapper.completeRunGuarded(runId, status, errorCode,
                errorDetail, failedTool, LocalDateTime.now());

        if (affected == 0) {
            // Run was already completed by another path (e.g. recovery scheduler)
            log.warn("completeRunGuarded returned 0 for run {} — stale callback rejected (run already terminal)",
                    runId);
            return;
        }

        // 同步更新 task 状态 — 守护：仅当 task.currentRunId == run.id
        AgentTask task = taskMapper.selectById(run.getTaskId());
        if (task != null) {
            if (task.getCurrentRunId() != null && task.getCurrentRunId().equals(runId)) {
                task.setStatus(status);
                taskMapper.updateById(task);
            } else {
                log.warn("Task {} currentRunId={} != run.id={} — skipping task status propagation",
                        task.getId(), task.getCurrentRunId(), runId);
            }
        }

        // Store the model/token usage/duration in the run entity for audit
        run.setStatus(status);
        if (tokenUsage != null) run.setTokenUsage(tokenUsage);
        run.setToolCallsCount(toolCallsCount);
        run.setDurationMs(actualDuration);

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

        // V13: 创建新 pending Run，Worker 自动执行
        List<AgentRun> existingRuns = runMapper.selectByTaskId(taskId);
        int attemptNumber = existingRuns.size() + 1;

        AgentRun newRun = new AgentRun();
        newRun.setTaskId(taskId);
        newRun.setRunUuid(java.util.UUID.randomUUID().toString());
        newRun.setAttemptNumber(attemptNumber);
        newRun.setStatus(AgentConstants.STATUS_PENDING);
        newRun.setScheduledAt(LocalDateTime.now()); // immediate
        newRun.setDispatchCount(1);
        newRun.setModel(existingRuns.isEmpty() ? null : existingRuns.get(existingRuns.size() - 1).getModel());
        newRun.setStyle("detailed");
        newRun.setMaxToolSteps(5);
        runMapper.insert(newRun);

        // 更新 task 状态
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(newRun.getId());
        taskMapper.updateById(task);

        log.info("Task {} retry scheduled: new run id={} attempt={}",
                taskId, newRun.getId(), attemptNumber);
        return newRun;
    }

    // ================================================================
    // V13: 队列调度
    // ================================================================

    @Override
    @Transactional
    public AgentRun enqueueRun(Long taskId) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new BusinessException("Agent任务不存在: " + taskId);
        }

        // Allow PENDING and RETRYABLE states to be queued
        if (!AgentConstants.STATUS_PENDING.equals(task.getStatus())
                && !AgentConstants.RETRYABLE_STATUSES.contains(task.getStatus())) {
            throw new BusinessException(String.format(
                    "无法入队：任务状态 %s 不允许创建新 Run", task.getStatus()));
        }

        // Compute attempt number
        List<AgentRun> existingRuns = runMapper.selectByTaskId(taskId);
        int attemptNumber = existingRuns.size() + 1;

        LocalDateTime now = LocalDateTime.now();
        AgentRun run = new AgentRun();
        run.setTaskId(taskId);
        run.setRunUuid(java.util.UUID.randomUUID().toString());
        run.setAttemptNumber(attemptNumber);
        run.setStatus(AgentConstants.STATUS_PENDING);
        run.setScheduledAt(now); // immediate execution
        run.setDispatchCount(1);
        run.setModel(existingRuns.isEmpty() ? null : existingRuns.get(existingRuns.size() - 1).getModel());
        run.setStyle("detailed");
        run.setMaxToolSteps(5);
        runMapper.insert(run);

        // Update task: pending, point to new run
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(run.getId());
        taskMapper.updateById(task);

        // Record QUEUED event
        statusEventService.record(taskId, run.getId(), "QUEUED",
                AgentConstants.STATUS_PENDING,
                Map.of("attemptNumber", attemptNumber, "runUuid", run.getRunUuid()));

        log.info("Task {} enqueued: run id={} uuid={} attempt={}", taskId, run.getId(), run.getRunUuid(), attemptNumber);
        return run;
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

        // V13: 增强取消 — 支持 pending/running/waiting_approval 状态
        String taskStatus = task.getStatus();
        if (AgentConstants.TERMINAL_STATUSES.contains(taskStatus)) {
            return false; // already terminal
        }

        // For running tasks with a worker, set Redis cancel flag
        if (AgentConstants.STATUS_RUNNING.equals(taskStatus) && task.getCurrentRunId() != null) {
            AgentRun currentRun = runMapper.selectById(task.getCurrentRunId());
            if (currentRun != null) {
                // Set Redis cancel flag (TTL 1h) — survives restart
                try {
                    redisUtils.set("agent:cancel:" + currentRun.getId(), "1",
                            cancelFlagTtlSeconds, java.util.concurrent.TimeUnit.SECONDS);
                } catch (Exception e) {
                    log.warn("Failed to set Redis cancel flag for run {}: {}",
                            currentRun.getId(), e.getMessage());
                }
                // Best-effort cancel the Python task
                try {
                    aiClient.cancelRequest(currentRun.getRunUuid());
                } catch (Exception ex) {
                    log.debug("Best-effort Python cancel for run {}: {}", currentRun.getId(), ex.getMessage());
                }
                cancelRun(currentRun.getId());
            }
        } else if (AgentConstants.STATUS_WAITING_APPROVAL.equals(taskStatus)) {
            // Cancel all pending approvals for this task
            List<AgentApproval> pendingApprovals = approvalMapper.selectByTaskId(taskId);
            for (AgentApproval approval : pendingApprovals) {
                if ("pending".equals(approval.getStatus())) {
                    String nowStr = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
                    approvalMapper.updateDecision(approval.getId(), "expired", null, nowStr, "用户取消任务");
                }
            }
            if (task.getCurrentRunId() != null) {
                cancelRun(task.getCurrentRunId());
            }
        } else if (AgentConstants.STATUS_PENDING.equals(taskStatus)) {
            // Pending task — mark task and current run as cancelled
            if (task.getCurrentRunId() != null) {
                cancelRun(task.getCurrentRunId());
            }
        }

        task.setStatus(AgentConstants.STATUS_CANCELLED);
        taskMapper.updateById(task);

        // Record status event
        statusEventService.record(taskId, task.getCurrentRunId(), "CANCELLED",
                AgentConstants.STATUS_CANCELLED, null);

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
        String toolInputHash = canonicalToolInputHash(toolInput != null ? toolInput : "{}");

        AgentApproval approval = new AgentApproval();
        approval.setApprovalId(java.util.UUID.randomUUID().toString());
        approval.setTaskId(taskId);
        approval.setRunId(runId);
        approval.setUserId(userId);
        approval.setUserRole(resolveUserRole(userId));
        approval.setTraceId(com.hfusionhub.config.TraceContext.getTraceId());
        approval.setToolName(toolName);
        approval.setToolInputHash(toolInputHash);
        approval.setToolInput(toolInput != null ? toolInput : "{}");
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
        int updated = approvalMapper.updateDecision(approval.getId(), newStatus, decidedBy,
                LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")), reason);
        if (updated != 1) {
            throw new BusinessException("审批已被其他请求处理");
        }

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
            // V13: record event
            statusEventService.record(approval.getTaskId(), approval.getRunId(),
                    "APPROVAL_DECIDED", AgentConstants.STATUS_FAILED,
                    Map.of("decision", "denied", "toolName", approval.getToolName()));
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
            // V13: record event
            statusEventService.record(approval.getTaskId(), approval.getRunId(),
                    "APPROVAL_DECIDED", AgentConstants.STATUS_RUNNING,
                    Map.of("decision", "approved", "toolName", approval.getToolName()));
            log.info("Approval {} APPROVED by user {}: tool={} (will call Python resume)",
                    approvalId, decidedBy, approval.getToolName());
        }

        approval.setStatus(newStatus);
        approval.setDecidedBy(decidedBy);
        approval.setReason(reason);

        // ── Issue a durable one-time execution token (durable single-execution).
        // Only the first approve can change the token from 'none' → 'issued'
        // (guarded in SQL against concurrent duplicates).  It is consumed by the
        // Java consume endpoint / Python decide before the tool runs, so a
        // replayed approve/resume can never execute the tool twice.
        String executionToken = null;
        if ("approved".equals(decision)) {
            executionToken = java.util.UUID.randomUUID().toString();
            try {
                int issued = approvalMapper.issueExecutionToken(
                        approval.getId(), executionToken, AgentConstants.EXECUTION_TOKEN_ISSUED,
                        LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));
                if (issued != 1) {
                    log.warn("Could not issue execution token for approval {} — approval not in issueable state", approvalId);
                    executionToken = null;
                }
            } catch (Exception e) {
                log.error("Failed to issue execution token for approval {}: {}", approvalId, e.getMessage());
                executionToken = null;
            }
        }

        // ── Phase 2: Call Python (outside any transaction — recordStep
        //        and completeRun manage their own transactions). ──
        if ("approved".equals(decision) && task != null && run != null) {
            try {
                resumeAgentAfterApproval(approval, task, run, executionToken);
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
    private void resumeAgentAfterApproval(AgentApproval approval, AgentTask task, AgentRun run,
                                          String executionToken) {
        Long runId = run.getId();
        // Build chat history from messages
        List<Map<String, String>> history = List.of();
        Long conversationId = task.getConversationId();
        if (conversationId != null) {
            history = getChatHistoryForTask(conversationId);
        }

        // Resume with the exact JSON captured at pause time, never the redacted summary.
        String toolInput = approval.getToolInput() != null ? approval.getToolInput() : "{}";
        if (!canonicalToolInputHash(toolInput).equalsIgnoreCase(approval.getToolInputHash())) {
            throw new BusinessException("审批参数校验失败");
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
                approval.getToolInputHash(),
                task.getQuery(),
                history,
                conversationId,
                run.getModel(),
                executionToken,
                approval.getUserRole()
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
    public AgentApproval getApprovalWithToken(String approvalId) {
        return approvalMapper.selectByApprovalId(approvalId);
    }

    @Override
    @Transactional
    public boolean consumeExecutionToken(String approvalId, String executionToken) {
        if (approvalId == null || executionToken == null || executionToken.isBlank()) {
            return false;
        }
        String consumedAt = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        int updated = approvalMapper.consumeExecutionToken(approvalId, executionToken, consumedAt);
        if (updated == 1) {
            log.info("Execution token consumed for approval {} (token={}...) — single execution granted",
                    approvalId, executionToken.substring(0, Math.min(8, executionToken.length())));
            return true;
        }
        log.warn("Execution token consume rejected for approval {} (already consumed / revoked / mismatch)",
                approvalId);
        return false;
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
                run.setErrorCode(AgentConstants.ERR_APPROVAL_EXPIRED);
                run.setErrorDetail("审批超时（5分钟未响应）");
                run.setCompletedAt(java.time.LocalDateTime.now());
                runMapper.updateById(run);
            }
            // V13: record event
            statusEventService.record(a.getTaskId(), a.getRunId(), "RUN_FAILED",
                    AgentConstants.STATUS_FAILED,
                    Map.of("errorCode", AgentConstants.ERR_APPROVAL_EXPIRED,
                            "errorDetail", "审批超时（5分钟未响应）"));
        }
        if (!expired.isEmpty()) {
            log.info("Expired {} pending approvals", expired.size());
        }
        return expired.size();
    }

    // ================================================================
    // V13: 死信恢复
    // ================================================================

    @Override
    @Transactional
    public AgentRun requeueTask(Long taskId, Long userId) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new BusinessException("任务不存在: " + taskId);
        }
        if (!task.getUserId().equals(userId)) {
            throw new BusinessException("无权操作此任务");
        }
        if (!AgentConstants.STATUS_DEAD_LETTER.equals(task.getStatus())) {
            throw new BusinessException("只能恢复死信任务，当前状态: " + task.getStatus());
        }

        // 清除死信字段
        task.setDeadLetterReason(null);
        task.setDeadLetterAt(null);

        // 创建新 pending Run
        List<AgentRun> existingRuns = runMapper.selectByTaskId(taskId);
        int attemptNumber = existingRuns.size() + 1;

        AgentRun newRun = new AgentRun();
        newRun.setTaskId(taskId);
        newRun.setRunUuid(java.util.UUID.randomUUID().toString());
        newRun.setAttemptNumber(attemptNumber);
        newRun.setStatus(AgentConstants.STATUS_PENDING);
        newRun.setScheduledAt(LocalDateTime.now()); // immediate
        newRun.setDispatchCount(1);
        newRun.setModel(existingRuns.isEmpty() ? null : existingRuns.get(existingRuns.size() - 1).getModel());
        newRun.setStyle("detailed");
        newRun.setMaxToolSteps(5);
        runMapper.insert(newRun);

        // 重置 task
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(newRun.getId());
        taskMapper.updateById(task);

        // Record event
        statusEventService.record(taskId, newRun.getId(), "RECOVERED",
                AgentConstants.STATUS_PENDING,
                Map.of("fromStatus", AgentConstants.STATUS_DEAD_LETTER,
                        "attemptNumber", attemptNumber));

        log.info("Dead-letter task {} requeued by user {}: new run id={} attempt={}",
                taskId, userId, newRun.getId(), attemptNumber);
        return newRun;
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

    private static String canonicalToolInputHash(String input) {
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            String canonical = mapper.writeValueAsString(sortJson(mapper.readTree(input == null ? "{}" : input)));
            return sha256(canonical);
        } catch (Exception e) {
            throw new BusinessException("invalid tool input");
        }
    }

    private static Object sortJson(com.fasterxml.jackson.databind.JsonNode node) {
        if (node.isObject()) {
            Map<String, Object> sorted = new java.util.TreeMap<>();
            node.fields().forEachRemaining(entry -> sorted.put(entry.getKey(), sortJson(entry.getValue())));
            return sorted;
        }
        if (node.isArray()) {
            List<Object> values = new java.util.ArrayList<>();
            node.forEach(value -> values.add(sortJson(value)));
            return values;
        }
        if (node.isTextual()) return node.textValue();
        if (node.isBoolean()) return node.booleanValue();
        if (node.isNumber()) return node.numberValue();
        if (node.isNull()) return null;
        throw new IllegalArgumentException("unsupported JSON node");
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
                    .scheduledAt(run.getScheduledAt())
                    .leaseHolder(run.getLeaseHolder())
                    .leaseExpiresAt(run.getLeaseExpiresAt())
                    .heartbeatAt(run.getHeartbeatAt())
                    .dispatchCount(run.getDispatchCount())
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
                .deadLetterReason(task.getDeadLetterReason())
                .deadLetterAt(task.getDeadLetterAt())
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

        boolean isDeadLetter = AgentConstants.STATUS_DEAD_LETTER.equals(task.getStatus());
        return AgentTaskSummaryDTO.builder()
                .id(task.getId())
                .requestId(task.getRequestId())
                .query(querySummary)
                .knowledgeBaseId(task.getKnowledgeBaseId())
                .status(task.getStatus())
                .deadLetter(isDeadLetter)
                .deadLetterReason(task.getDeadLetterReason())
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

    /**
     * Resolve a user's role for policy evaluation (approval target context).
     * Defaults to {@code "user"} when the account cannot be read.
     */
    private String resolveUserRole(Long userId) {
        try {
            if (userId == null) return "user";
            com.hfusionhub.entity.User user = userMapper.selectById(userId);
            if (user != null && user.getRole() != null && !user.getRole().isBlank()) {
                return user.getRole();
            }
        } catch (Exception e) {
            log.debug("resolveUserRole({}) failed — defaulting to user: {}", userId, e.getMessage());
        }
        return "user";
    }
}
