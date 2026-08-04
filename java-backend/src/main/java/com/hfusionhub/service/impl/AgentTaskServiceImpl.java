package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.config.QuotaProperties;
import com.hfusionhub.dto.AgentRunDTO;
import com.hfusionhub.dto.AgentStepDTO;
import com.hfusionhub.dto.AgentTaskDetailDTO;
import com.hfusionhub.dto.AgentTaskSummaryDTO;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentStep;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.entity.ModelUsageRecord;
import com.hfusionhub.mapper.AgentApprovalMapper;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.AgentTaskService;
import com.hfusionhub.service.CostTrackingService;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Lazy;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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
    private final UserMapper userMapper;
    private final AiClient aiClient;
    private final com.hfusionhub.service.AgentTaskQueueService queueService;
    private final com.hfusionhub.service.AgentStatusEventService statusEventService;
    private final com.hfusionhub.common.utils.RedisUtils redisUtils;
    private final UsageLedgerService usageLedgerService;
    private final QuotaProperties quotaProperties;
    private final CostTrackingService costTrackingService;
    private final AgentRunLifecycleService runLifecycle;

    @SuppressWarnings("java:S107")
    public AgentTaskServiceImpl(
            AgentTaskMapper taskMapper,
            AgentRunMapper runMapper,
            AgentStepMapper stepMapper,
            AgentApprovalMapper approvalMapper,
            UserMapper userMapper,
            AiClient aiClient,
            @Lazy com.hfusionhub.service.AgentTaskQueueService queueService,
            com.hfusionhub.service.AgentStatusEventService statusEventService,
            com.hfusionhub.common.utils.RedisUtils redisUtils,
            UsageLedgerService usageLedgerService,
            QuotaProperties quotaProperties,
            CostTrackingService costTrackingService,
            AgentRunLifecycleService runLifecycle) {
        this.taskMapper = taskMapper;
        this.runMapper = runMapper;
        this.stepMapper = stepMapper;
        this.approvalMapper = approvalMapper;
        this.userMapper = userMapper;
        this.aiClient = aiClient;
        this.queueService = queueService;
        this.statusEventService = statusEventService;
        this.redisUtils = redisUtils;
        this.usageLedgerService = usageLedgerService;
        this.quotaProperties = quotaProperties;
        this.costTrackingService = costTrackingService;
        this.runLifecycle = runLifecycle;
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
    public AgentTask createTask(String requestId, Long userId, Long conversationId, Long kbId, String query) {
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
    public AgentRun startRun(Long taskId, String runUuid, String model, String style, int maxToolSteps) {
        return startRun(taskId, runUuid, model, style, maxToolSteps, null);
    }

    @Override
    @Transactional
    public AgentRun startRun(
            Long taskId, String runUuid, String model, String style, int maxToolSteps, String leaseHolder) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) {
            throw new BusinessException("Agent任务不存在: " + taskId);
        }

        // 校验状态转移：pending → running
        if (!AgentConstants.canTransition(task.getStatus(), AgentConstants.STATUS_RUNNING)) {
            throw new BusinessException(
                    String.format("无法启动运行：任务状态 %s 不允许转移为 %s", task.getStatus(), AgentConstants.STATUS_RUNNING));
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

        // 用量账本：预占 AGENT_TOKENS（幂等键 agent_run:<runUuid>）。
        // 流式路径在请求线程调用，当前 TenantContext 已就绪。
        reserveAgentRunUsage(run.getId());

        log.info(
                "Started agent run id={} uuid={} attempt={} for task={} leaseHolder={}",
                run.getId(),
                runUuid,
                attemptNumber,
                taskId,
                leaseHolder);
        return run;
    }

    @Override
    @Transactional
    public void recordStep(
            Long runId,
            int sequence,
            String stepType,
            String action,
            String inputSummary,
            String outputSummary,
            List<Map<String, Object>> sources,
            long durationMs,
            String errorCode) {
        // 幂等：相同 (runId, sequence) 不重复插入
        AgentStep existing = stepMapper.selectOne(new LambdaQueryWrapper<AgentStep>()
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
    public void completeRun(
            Long runId,
            String status,
            String model,
            Map<String, Object> tokenUsage,
            int toolCallsCount,
            long durationMs,
            String errorCode,
            String errorDetail,
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

        // 计算实际耗时（时钟回拨防护见 clampDuration；负耗时入库会经
        // model_usage_record.latency_ms 传导到运营数仓，被质量门禁 R4 拦截）
        long actualDuration = AgentTaskSupport.clampDuration(durationMs, run.getStartedAt());

        // V13: 守护终态写入 — 仅 running/waiting_approval → 终态
        int affected =
                runMapper.completeRunGuarded(runId, status, errorCode, errorDetail, failedTool, LocalDateTime.now());

        if (affected == 0) {
            // Run was already completed by another path (e.g. recovery scheduler)
            log.warn(
                    "completeRunGuarded returned 0 for run {} — stale callback rejected (run already terminal)", runId);
            return;
        }

        // 用量账本：终态结算/退回（succeeded 结算，其余退回）。幂等。
        finalizeAgentRunUsage(runId, status, tokenUsage);

        // 同步更新 task 状态 — 守护：仅当 task.currentRunId == run.id
        AgentTask task = taskMapper.selectById(run.getTaskId());
        if (task != null) {
            if (task.getCurrentRunId() != null && task.getCurrentRunId().equals(runId)) {
                task.setStatus(status);
                taskMapper.updateById(task);
            } else {
                log.warn(
                        "Task {} currentRunId={} != run.id={} — skipping task status propagation",
                        task.getId(),
                        task.getCurrentRunId(),
                        runId);
            }
        }

        // Store the model/token usage/duration in the run entity for audit
        run.setStatus(status);
        if (tokenUsage != null) run.setTokenUsage(tokenUsage);
        run.setToolCallsCount(toolCallsCount);
        run.setDurationMs(actualDuration);
        runMapper.updateCompletionMetadata(runId, model, tokenUsage, toolCallsCount, actualDuration);

        // 模型用量落账（model_usage_record）：Agent 运行终态记录真实 token 用量。
        recordAgentModelUsage(run, task, tokenUsage, model);

        log.info(
                "Agent run {} completed: status={} duration={}ms toolCalls={}",
                runId,
                status,
                actualDuration,
                toolCallsCount);
    }

    /**
     * Agent 运行终态时记录模型用量到 model_usage_record（成本追踪）。
     * 记录失败仅告警，不影响主流程。task 可能为 null（如孤儿 run），此时跳过。
     */
    private void recordAgentModelUsage(AgentRun run, AgentTask task, Map<String, Object> tokenUsage, String model) {
        try {
            if (task == null || task.getUserId() == null) {
                return;
            }
            ModelUsageRecord rec = new ModelUsageRecord();
            rec.setUserId(task.getUserId());
            rec.setTenantId(run.getTenantId());
            rec.setAgentTaskId(task.getId());
            rec.setConversationId(task.getConversationId());
            String resolvedModel = model;
            if (resolvedModel == null || resolvedModel.isBlank()) {
                resolvedModel = run.getModel();
            }
            if (resolvedModel == null || resolvedModel.isBlank()) {
                resolvedModel = "unknown";
            }
            rec.setModel(resolvedModel);
            rec.setProvider(resolvedModel);
            rec.setRequestType("agent");
            int prompt = 0;
            int completion = 0;
            int total = 0;
            if (tokenUsage != null) {
                prompt = usageInt(tokenUsage.get("prompt_tokens"));
                completion = usageInt(tokenUsage.get("completion_tokens"));
                total = usageInt(tokenUsage.get("total_tokens"));
                if (total <= 0) {
                    total = prompt + completion;
                }
            }
            rec.setPromptTokens(prompt);
            rec.setCompletionTokens(completion);
            rec.setTotalTokens(total);
            rec.setCostUsd(BigDecimal.ZERO);
            rec.setLatencyMs(run.getDurationMs() != null ? run.getDurationMs().intValue() : 0);
            costTrackingService.record(rec);
            log.debug(
                    "Agent model usage recorded: runId={} userId={} model={} tokens={}",
                    run.getId(),
                    task.getUserId(),
                    resolvedModel,
                    total);
        } catch (Exception e) {
            log.warn("Failed to record agent model usage (non-blocking): {}", e.getMessage());
        }
    }

    private static int usageInt(Object value) {
        return value instanceof Number n ? n.intValue() : 0;
    }

    @Override
    @Transactional
    public void failRun(Long runId, String errorCode, String errorDetail, String failedTool) {
        completeRun(runId, AgentConstants.STATUS_FAILED, null, null, 0, 0, errorCode, errorDetail, failedTool);
    }

    @Override
    @Transactional
    public void cancelRun(Long runId) {
        completeRun(
                runId, AgentConstants.STATUS_CANCELLED, null, null, 0, 0, AgentConstants.ERR_CANCELLED, "用户取消", null);
    }

    @Override
    @Transactional
    public void reserveAgentRunUsage(Long runId) {
        AgentRun run = runMapper.selectById(runId);
        if (run == null || run.getRunUuid() == null) {
            throw new BusinessException("Agent run does not exist or has no run UUID: " + runId);
        }
        AgentTask task = taskMapper.selectById(run.getTaskId());
        Long tenantId = runLifecycle.resolveRunTenant(run, task);
        if (tenantId == null) {
            throw new BusinessException("Cannot execute agent run without a resolvable tenant: " + runId);
        }
        // Backfill legacy runs so subsequent worker code and finalization use
        // the same durable tenant identity, rather than a thread-local value.
        if (run.getTenantId() == null) {
            run.setTenantId(tenantId);
            runMapper.updateById(run);
        }
        String query = task != null ? task.getQuery() : null;
        int maxToolSteps = run.getMaxToolSteps() != null ? run.getMaxToolSteps() : 5;
        long estimate = estimateAgentTokens(query, maxToolSteps);
        final Long tenant = tenantId;
        final String usageKey = "agent_run:" + run.getRunUuid();
        TenantContext.runAs(tenant, () -> {
            usageLedgerService.reserve(UsageMeter.AGENT_TOKENS, usageKey, estimate, "agent_run", String.valueOf(runId));
            return null;
        });
    }

    @Override
    @Transactional
    public void finalizeAgentRunUsage(Long runId, String status, Map<String, Object> tokenUsage) {
        // 已收口到 AgentRunLifecycleService（守卫迁移 + 账本结算统一入口）
        runLifecycle.finalizeAgentRunUsage(runId, status, tokenUsage);
    }

    /**
     * Agent 用量预占估算：输入按内容长度粗估（至少 64），
     * 上界追加 输出上限 × (maxToolSteps + 1)（多步工具调用各计一次输出）。
     */
    private long estimateAgentTokens(String query, int maxToolSteps) {
        long inputEstimate = Math.max(64, (query == null ? 0 : query.length()) / 4);
        int steps = Math.max(1, maxToolSteps);
        return inputEstimate + quotaProperties.getChatMaxOutputTokens() * (steps + 1L);
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
    public PageResult<AgentTaskSummaryDTO> listUserTasks(Long userId, String status, int page, int pageSize) {
        int offset = (page - 1) * pageSize;
        List<AgentTask> tasks = taskMapper.selectByUserIdAndStatus(userId, status, offset, pageSize);
        int total = taskMapper.countByUserIdAndStatus(userId, status);

        List<AgentTaskSummaryDTO> summaries =
                tasks.stream().map(this::buildSummary).collect(Collectors.toList());

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
        // V77/S4: 行锁串行化同一任务的并发重试
        AgentTask task = taskMapper.selectByIdForUpdate(taskId);
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
        AgentRun newRun = insertPendingRun(taskId, existingRunsModel(taskId), "RETRY");

        // 更新 task 状态
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(newRun.getId());
        taskMapper.updateById(task);

        log.info("Task {} retry scheduled: new run id={} attempt={}", taskId, newRun.getId(), newRun.getAttemptNumber());
        return newRun;
    }

    /**
     * V77/S4: 创建 pending Run。attempt 取 MAX(attempt_number)+1（行锁下无 TOCTOU），
     * 并以 V77 唯一索引 (task_id, attempt_number) 兜底：并发双重入队时第二条插入
     * 触发 DuplicateKeyException，转友好冲突错误并回滚。
     */
    private AgentRun insertPendingRun(Long taskId, String inheritedModel, String action) {
        int attemptNumber = runMapper.selectMaxAttemptNumber(taskId) + 1;
        AgentRun run = new AgentRun();
        run.setTaskId(taskId);
        run.setRunUuid(java.util.UUID.randomUUID().toString());
        run.setAttemptNumber(attemptNumber);
        run.setStatus(AgentConstants.STATUS_PENDING);
        run.setScheduledAt(LocalDateTime.now()); // immediate execution
        run.setDispatchCount(1);
        run.setModel(inheritedModel);
        run.setStyle("detailed");
        run.setMaxToolSteps(5);
        try {
            runMapper.insert(run);
        } catch (DuplicateKeyException e) {
            log.warn("Task {} {} rejected: duplicate attempt {} (concurrent enqueue/retry)", taskId, action, attemptNumber);
            throw new BusinessException("任务正在重试中，请勿重复操作");
        }
        return run;
    }

    private String existingRunsModel(Long taskId) {
        List<AgentRun> existingRuns = runMapper.selectByTaskId(taskId);
        return existingRuns.isEmpty() ? null : existingRuns.get(existingRuns.size() - 1).getModel();
    }

    // ================================================================
    // V13: 队列调度
    // ================================================================

    @Override
    @Transactional
    public AgentRun enqueueRun(Long taskId) {
        // V77/S4: 行锁串行化同一任务的并发入队/重试/恢复
        AgentTask task = taskMapper.selectByIdForUpdate(taskId);
        if (task == null) {
            throw new BusinessException("Agent任务不存在: " + taskId);
        }

        // Allow PENDING and RETRYABLE states to be queued
        if (!AgentConstants.STATUS_PENDING.equals(task.getStatus())
                && !AgentConstants.RETRYABLE_STATUSES.contains(task.getStatus())) {
            throw new BusinessException(String.format("无法入队：任务状态 %s 不允许创建新 Run", task.getStatus()));
        }

        AgentRun run = insertPendingRun(taskId, existingRunsModel(taskId), "QUEUED");
        int attemptNumber = run.getAttemptNumber();

        // Update task: pending, point to new run
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(run.getId());
        taskMapper.updateById(task);

        // Record QUEUED event
        statusEventService.record(
                taskId,
                run.getId(),
                "QUEUED",
                AgentConstants.STATUS_PENDING,
                Map.of("attemptNumber", attemptNumber, "runUuid", run.getRunUuid()));

        log.info(
                "Task {} enqueued: run id={} uuid={} attempt={}", taskId, run.getId(), run.getRunUuid(), attemptNumber);
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
                    redisUtils.set(
                            "agent:cancel:" + currentRun.getId(),
                            "1",
                            cancelFlagTtlSeconds,
                            java.util.concurrent.TimeUnit.SECONDS);
                } catch (Exception e) {
                    log.warn("Failed to set Redis cancel flag for run {}: {}", currentRun.getId(), e.getMessage());
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
        statusEventService.record(taskId, task.getCurrentRunId(), "CANCELLED", AgentConstants.STATUS_CANCELLED, null);

        log.info("Task {} cancelled by user {}", taskId, userId);
        return true;
    }

    // ================================================================
    // Agent V1 Step 5: 审批方法
    // ================================================================

    @Override
    @Transactional
    public AgentApproval pauseForApproval(
            Long taskId,
            Long runId,
            Long userId,
            String toolName,
            String toolInput,
            String argumentsSummary,
            String riskLevel) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null) throw new BusinessException("任务不存在: " + taskId);

        // 状态转移: running → waiting_approval
        if (!AgentConstants.canTransition(task.getStatus(), AgentConstants.STATUS_WAITING_APPROVAL)) {
            throw new BusinessException("当前状态不允许转入等待审批: " + task.getStatus());
        }

        // 计算参数哈希（审批令牌绑定）
        String toolInputHash = AgentTaskSupport.canonicalToolInputHash(toolInput != null ? toolInput : "{}");

        AgentApproval approval = new AgentApproval();
        approval.setApprovalId(java.util.UUID.randomUUID().toString());
        approval.setTaskId(taskId);
        approval.setRunId(runId);
        approval.setUserId(userId);
        approval.setUserRole(resolveUserRole(userId));
        approval.setTraceId(com.hfusionhub.config.TraceContext.getTraceId());
        approval.setToolName(toolName);
        approval.setRiskLevel(riskLevel != null && !riskLevel.isBlank() ? riskLevel : "read_only");
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

        log.info("Task {} paused for approval: approvalId={} tool={}", taskId, approval.getApprovalId(), toolName);
        return approval;
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
            log.info(
                    "Execution token consumed for approval {} (token={}...) — single execution granted",
                    approvalId,
                    executionToken.substring(0, Math.min(8, executionToken.length())));
            return true;
        }
        log.warn(
                "Execution token consume rejected for approval {} (already consumed / revoked / mismatch)", approvalId);
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
        if (expired.isEmpty()) {
            return 0;
        }

        // R15-17：批量读取 task/run（旧实现每条审批 2 次单查）；更新仍逐条。
        java.util.Set<Long> taskIds = new java.util.HashSet<>();
        java.util.Set<Long> runIds = new java.util.HashSet<>();
        for (AgentApproval a : expired) {
            if (a.getTaskId() != null) taskIds.add(a.getTaskId());
            if (a.getRunId() != null) runIds.add(a.getRunId());
        }
        java.util.Map<Long, AgentTask> taskMap = taskIds.isEmpty() ? java.util.Map.of()
                : taskMapper.selectBatchIds(taskIds).stream()
                        .collect(java.util.stream.Collectors.toMap(AgentTask::getId, t -> t));
        java.util.Map<Long, AgentRun> runMap = runIds.isEmpty() ? java.util.Map.of()
                : runMapper.selectBatchIds(runIds).stream()
                        .collect(java.util.stream.Collectors.toMap(AgentRun::getId, r -> r));

        for (AgentApproval a : expired) {
            approvalMapper.updateDecision(a.getId(), "expired", null, nowStr, "审批超时自动拒绝");
            // 更新 task → failed
            AgentTask task = taskMap.get(a.getTaskId());
            if (task != null && AgentConstants.STATUS_WAITING_APPROVAL.equals(task.getStatus())) {
                task.setStatus(AgentConstants.STATUS_FAILED);
                taskMapper.updateById(task);
            }
            AgentRun run = runMap.get(a.getRunId());
            // S3/M3 行锁升级：与 decideApproval 的双向竞态由条件 UPDATE 行级判定——
            // 用户刚批准（run 已 RUNNING）的任务不会被过期调度覆盖为 FAILED
            if (run != null && runLifecycle.failFromWaitingApproval(
                    run.getId(),
                    AgentConstants.ERR_APPROVAL_EXPIRED,
                    "审批超时（5分钟未响应）")) {
                finalizeAgentRunUsage(run.getId(), AgentConstants.STATUS_FAILED, null);
            }
            // V13: record event
            statusEventService.record(
                    a.getTaskId(),
                    a.getRunId(),
                    "RUN_FAILED",
                    AgentConstants.STATUS_FAILED,
                    Map.of("errorCode", AgentConstants.ERR_APPROVAL_EXPIRED, "errorDetail", "审批超时（5分钟未响应）"));
        }
        log.info("Expired {} pending approvals", expired.size());
        return expired.size();
    }

    // ================================================================
    // V13: 死信恢复
    // ================================================================

    @Override
    @Transactional
    public AgentRun requeueTask(Long taskId, Long userId) {
        // V77/S4: 行锁串行化同一任务的并发恢复
        AgentTask task = taskMapper.selectByIdForUpdate(taskId);
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
        AgentRun newRun = insertPendingRun(taskId, existingRunsModel(taskId), "RECOVER");
        int attemptNumber = newRun.getAttemptNumber();

        // 重置 task
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(newRun.getId());
        taskMapper.updateById(task);

        // Record event
        statusEventService.record(
                taskId,
                newRun.getId(),
                "RECOVERED",
                AgentConstants.STATUS_PENDING,
                Map.of("fromStatus", AgentConstants.STATUS_DEAD_LETTER, "attemptNumber", attemptNumber));

        log.info(
                "Dead-letter task {} requeued by user {}: new run id={} attempt={}",
                taskId,
                userId,
                newRun.getId(),
                attemptNumber);
        return newRun;
    }

    // ================================================================
    // 内部辅助方法
    // ================================================================

    private AgentTaskDetailDTO buildDetail(AgentTask task) {
        List<AgentRun> runs = runMapper.selectByTaskId(task.getId());

        List<AgentRunDTO> runDTOs = runs.stream()
                .map(run -> {
                    List<AgentStep> steps = stepMapper.selectByRunId(run.getId());
                    List<AgentStepDTO> stepDTOs = steps.stream()
                            .map(step -> AgentStepDTO.builder()
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
                                    .build())
                            .collect(Collectors.toList());

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
                })
                .collect(Collectors.toList());

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
