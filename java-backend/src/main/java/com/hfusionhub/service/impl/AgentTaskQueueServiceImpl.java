package com.hfusionhub.service.impl;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.common.utils.RedisUtils;
import com.hfusionhub.entity.AgentRecoveryEvent;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.entity.Message;
import com.hfusionhub.mapper.AgentRecoveryEventMapper;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.service.AgentRetryPolicy;
import com.hfusionhub.service.AgentStatusEventService;
import com.hfusionhub.service.AgentStreamEventProcessor;
import com.hfusionhub.service.AgentTaskQueueService;
import com.hfusionhub.service.AgentTaskService;
import com.hfusionhub.service.ConversationService;
import com.hfusionhub.service.TaskEventSseManager;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Lazy;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;

/**
 * Agent 任务队列服务实现 — Worker 核心
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
public class AgentTaskQueueServiceImpl implements AgentTaskQueueService {

    private final AgentTaskMapper taskMapper;
    private final AgentRunMapper runMapper;
    private final AgentStepMapper stepMapper;
    private final AgentRecoveryEventMapper recoveryEventMapper;
    private final AgentTaskService agentTaskService;
    private final AgentStreamEventProcessor streamEventProcessor;
    private final ConversationService conversationService;
    private final AgentStatusEventService statusEventService;
    private final AgentRetryPolicy retryPolicy;
    private final AiClient aiClient;
    private final RedisUtils redisUtils;
    private final MessageMapper messageMapper;
    private final TaskEventSseManager sseManager;

    @Qualifier("agentWorkerExecutor")
    private final java.util.concurrent.Executor agentWorkerExecutor;

    @SuppressWarnings("java:S107")
    public AgentTaskQueueServiceImpl(
            AgentTaskMapper taskMapper,
            AgentRunMapper runMapper,
            AgentStepMapper stepMapper,
            AgentRecoveryEventMapper recoveryEventMapper,
            @Lazy AgentTaskService agentTaskService,
            AgentStreamEventProcessor streamEventProcessor,
            @Lazy ConversationService conversationService,
            AgentStatusEventService statusEventService,
            AgentRetryPolicy retryPolicy,
            AiClient aiClient,
            RedisUtils redisUtils,
            MessageMapper messageMapper,
            @Lazy TaskEventSseManager sseManager,
            @Qualifier("agentWorkerExecutor") java.util.concurrent.Executor agentWorkerExecutor) {
        this.taskMapper = taskMapper;
        this.runMapper = runMapper;
        this.stepMapper = stepMapper;
        this.recoveryEventMapper = recoveryEventMapper;
        this.agentTaskService = agentTaskService;
        this.streamEventProcessor = streamEventProcessor;
        this.conversationService = conversationService;
        this.statusEventService = statusEventService;
        this.retryPolicy = retryPolicy;
        this.aiClient = aiClient;
        this.redisUtils = redisUtils;
        this.messageMapper = messageMapper;
        this.sseManager = sseManager;
        this.agentWorkerExecutor = agentWorkerExecutor;
    }

    @Value("${agent.run.lease-seconds:120}")
    private int leaseSeconds;

    @Value("${agent.run.timeout-seconds:180}")
    private int timeoutSeconds;

    @Value("${agent.worker.batch-size:5}")
    private int batchSize;

    @Value("${agent.cancel-flag-ttl-seconds:3600}")
    private int cancelFlagTtlSeconds;

    @Value("${agent.instance-id:}")
    private String instanceId;

    /** 当前正在执行的 Run（runId → leaseHolder），用于心跳续租 */
    private final ConcurrentMap<Long, String> inflightRuns = new ConcurrentHashMap<>();
    private volatile String generatedWorkerId;

    /** 取消标志 Redis Key 前缀 */
    private static final String CANCEL_KEY_PREFIX = "agent:cancel:";

    // ================================================================
    // 队列轮询与派发
    // ================================================================

    @Override
    public int pollAndDispatch() {
        String workerId = getWorkerId();
        List<AgentRun> queued = runMapper.selectQueuedRuns(LocalDateTime.now(), batchSize);
        int dispatched = 0;
        for (AgentRun run : queued) {
            LocalDateTime now = LocalDateTime.now();
            LocalDateTime leaseExpires = now.plusSeconds(leaseSeconds);
            int claimed = runMapper.claimRun(run.getId(), workerId, leaseExpires, now, now);
            if (claimed > 0) {
                // Record QUEUED → RUN_STARTED event and update task to running
                AgentTask task = taskMapper.selectById(run.getTaskId());
                if (task != null) {
                    task.setStatus(AgentConstants.STATUS_RUNNING);
                    taskMapper.updateById(task);
                    statusEventService.record(task.getId(), run.getId(), "RUN_STARTED", AgentConstants.STATUS_RUNNING, null);
                }
                inflightRuns.put(run.getId(), workerId);
                final Long runIdToExecute = run.getId();
                java.util.concurrent.CompletableFuture.runAsync(
                        () -> executeRun(runIdToExecute, workerId), agentWorkerExecutor);
                dispatched++;
                log.info("Worker {} claimed run id={} uuid={} taskId={}",
                        workerId, run.getId(), run.getRunUuid(), run.getTaskId());
            }
        }
        return dispatched;
    }

    // ================================================================
    // Worker 执行主体
    // ================================================================

    private void executeRun(Long runId, String workerId) {
        AgentRun run = null;
        AgentTask task = null;

        try {
            // 1. Re-read run state
            run = runMapper.selectById(runId);
            if (run == null) return;

            // Verify lease ownership
            if (!workerId.equals(run.getLeaseHolder())) {
                log.debug("Run {} lease superseded: holder changed to {}", runId, run.getLeaseHolder());
                return;
            }
            if (!AgentConstants.STATUS_RUNNING.equals(run.getStatus())) {
                log.debug("Run {} no longer running: status={}", runId, run.getStatus());
                return;
            }

            // Check cancel flag
            if (isRunCancelled(runId)) {
                convergeCancel(run);
                return;
            }

            // 2. Verify task ownership
            task = taskMapper.selectById(run.getTaskId());
            if (task == null) {
                log.warn("Run {} has no associated task", runId);
                return;
            }
            if (task.getCurrentRunId() == null || !task.getCurrentRunId().equals(runId)) {
                markSuperseded(run);
                return;
            }

            // 3. Build chat history and call AI
            List<Map<String, String>> history = List.of();
            if (task.getConversationId() != null) {
                try {
                    history = conversationService.getChatHistoryWithInstructions(
                            task.getConversationId(), task.getUserId(), task.getQuery());
                } catch (Exception e) {
                    log.warn("Failed to get chat history for conversation {}: {}",
                            task.getConversationId(), e.getMessage());
                }
            }

            log.info("Worker {} executing run id={} uuid={} taskId={} attempt={}",
                    workerId, runId, run.getRunUuid(), task.getId(), run.getAttemptNumber());

            // 4. Call Python via SSE stream — choose endpoint based on KB binding
            final boolean isKbBound = task.getKnowledgeBaseId() != null
                    && task.getKnowledgeBaseId() > 0;
            reactor.core.publisher.Flux<String> sseFlux;
            if (isKbBound) {
                sseFlux = aiClient.agentV1ChatStream(
                        task.getQuery(),
                        task.getConversationId(),
                        task.getKnowledgeBaseId(),
                        history,
                        run.getRunUuid(),  // run_uuid as request_id for Python cancel/tracking
                        task.getUserId(),
                        null  // capability profile — worker uses default read-only
                );
            } else {
                // Non-KB chat: use standard /api/chat/stream
                sseFlux = aiClient.streamChat(
                        task.getQuery(),
                        task.getConversationId(),
                        task.getKnowledgeBaseId(),
                        history,
                        run.getRunUuid()   // run_uuid as request_id
                );
            }

            sseFlux = sseFlux.timeout(java.time.Duration.ofSeconds(timeoutSeconds));

            // 5. Subscribe to SSE stream with content accumulation + SSE broadcasting
            final AgentRun executingRun = run;
            final AgentTask executingTask = task;
            final Long taskId = task.getId();
            java.util.concurrent.CountDownLatch latch = new java.util.concurrent.CountDownLatch(1);
            java.util.concurrent.atomic.AtomicBoolean terminalReceived = new java.util.concurrent.atomic.AtomicBoolean(false);
            java.util.concurrent.atomic.AtomicReference<Throwable> streamError =
                    new java.util.concurrent.atomic.AtomicReference<>();
            StringBuilder responseBuilder = new StringBuilder();
            java.util.List<Map<String, Object>> accumulatedSources = new java.util.ArrayList<>();
            final com.fasterxml.jackson.databind.ObjectMapper objectMapper = new com.fasterxml.jackson.databind.ObjectMapper();

            reactor.core.Disposable subscription = sseFlux.subscribe(
                    chunk -> {
                        if (isRunCancelled(runId)) {
                            terminalReceived.set(true);
                            convergeCancel(executingRun);
                            latch.countDown();
                            return;
                        }
                        // Normalise the raw payload
                        String data = AgentStreamEventProcessor.stripSsePrefix(chunk);
                        if (data == null) return;

                        // [DONE] sentinel
                        if ("[DONE]".equals(data)) {
                            terminalReceived.set(true);
                            latch.countDown();
                            return;
                        }

                        try {
                            com.fasterxml.jackson.databind.JsonNode node = objectMapper.readTree(data);

                            // Structured event → process through shared event handler
                            if (node.has("event")) {
                                streamEventProcessor.handleLine(chunk, runId);
                                String eventType = node.get("event").asText();
                                if ("run_completed".equals(eventType) || "run_error".equals(eventType)) {
                                    terminalReceived.set(true);
                                    latch.countDown();
                                }
                                return;
                            }

                            // Cancelled flag from Python
                            boolean isCancelled = node.has("cancelled") && node.get("cancelled").asBoolean();
                            if (isCancelled) {
                                log.info("Python AI cancelled request for run {}", runId);
                                agentTaskService.cancelRun(runId);
                                terminalReceived.set(true);
                                latch.countDown();
                                return;
                            }

                            // Content chunk → accumulate + broadcast to SSE
                            String content = node.has("content") ? node.get("content").asText() : "";
                            if (!content.isEmpty()) {
                                responseBuilder.append(content);
                                sseManager.broadcastContentChunk(taskId, content);
                            }

                            // Sources → accumulate + broadcast
                            com.fasterxml.jackson.databind.JsonNode sourcesNode = node.get("sources");
                            if (sourcesNode != null && sourcesNode.isArray() && sourcesNode.size() > 0) {
                                java.util.List<Map<String, Object>> newSources =
                                        objectMapper.treeToValue(sourcesNode, java.util.List.class);
                                accumulatedSources.addAll(newSources);
                                sseManager.broadcastSources(taskId, newSources);
                            }
                        } catch (Exception ignored) {}
                    },
                    error -> {
                        streamError.set(error);
                        log.error("Worker SSE error for run {}: {}", runId, error.getMessage());
                        latch.countDown();
                    },
                    () -> {
                        latch.countDown();
                    }
            );

            // Wait for stream completion with a bounded execution timeout.
            boolean finished = false;
            try {
                finished = latch.await(timeoutSeconds, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                subscription.dispose();
            }

            Throwable terminalError = streamError.get();
            boolean streamTimedOut = terminalError instanceof java.util.concurrent.TimeoutException
                    || (terminalError != null && terminalError.getMessage() != null
                    && terminalError.getMessage().toLowerCase(java.util.Locale.ROOT).contains("timeout"));
            if (!finished || streamTimedOut) {
                handleExecutionTimeout(executingRun, executingTask, subscription, runId, workerId);
                return;
            }

            // 6. Save assistant message if content was accumulated (non-KB chat)
            if (responseBuilder.length() > 0 && executingTask.getConversationId() != null) {
                String assistantRequestId = executingTask.getRequestId()
                        + ConversationServiceImpl.ASSISTANT_REQUEST_SUFFIX;
                try {
                    Message existing = messageMapper.selectOne(
                            new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<Message>()
                                    .eq(Message::getRequestId, assistantRequestId));
                    if (existing == null) {
                        Message assistantMessage = new Message();
                        assistantMessage.setConversationId(executingTask.getConversationId());
                        assistantMessage.setRole("assistant");
                        assistantMessage.setContent(responseBuilder.toString());
                        assistantMessage.setModel("streaming");
                        assistantMessage.setTokenCount(0);
                        assistantMessage.setSources(accumulatedSources.isEmpty() ? null : accumulatedSources);
                        assistantMessage.setRequestId(assistantRequestId);
                        try {
                            messageMapper.insert(assistantMessage);
                            log.info("Worker saved assistant message for task {} len={}", taskId, responseBuilder.length());
                        } catch (DuplicateKeyException e) {
                            log.debug("Assistant message already exists for task {}", taskId);
                        }
                    }
                } catch (Exception e) {
                    log.warn("Failed to save assistant message for task {}: {}", taskId, e.getMessage());
                }
            }

            // 7. Broadcast DONE to SSE listeners
            sseManager.broadcastDone(taskId);

            // 8. Safety net: if no terminal event was received, converge
            if (!terminalReceived.get()) {
                AgentRun finalRun = runMapper.selectById(runId);
                if (finalRun != null && AgentConstants.STATUS_RUNNING.equals(finalRun.getStatus())) {
                    log.warn("Run {} completed SSE but no terminal event — forcing failed", runId);
                    agentTaskService.failRun(runId, "internal_error",
                            "Stream completed without terminal event; forced convergence", null);
                    // Handle terminal failure (retry/dead-letter)
                    AgentTask currentTask = taskMapper.selectById(finalRun.getTaskId());
                    if (currentTask != null) {
                        handleTerminalFailure(currentTask, finalRun, "internal_error",
                                "Stream completed without terminal event");
                    }
                }
            }

        } catch (Exception e) {
            log.error("Worker execution error for run {}: {}", runId, e.getMessage(), e);
            if (run != null) {
                try {
                    agentTaskService.failRun(runId, "internal_error",
                            e.getMessage() != null ? e.getMessage() : "Worker execution error", null);
                } catch (Exception failEx) {
                    log.error("Failed to mark run {} as failed after worker error: {}", runId, failEx.getMessage());
                }
                if (task == null) {
                    task = taskMapper.selectById(run.getTaskId());
                }
                if (task != null) {
                    handleTerminalFailure(task, run, "internal_error",
                            e.getMessage() != null ? e.getMessage() : "Worker execution error");
                }
            }
        } finally {
            inflightRuns.remove(runId);
            if (run != null) {
                runMapper.releaseLease(runId, workerId);
            }
        }
    }

    // ================================================================
    // 终态处理：重试 or 死信
    // ================================================================

    private void handleExecutionTimeout(AgentRun run, AgentTask task,
                                        reactor.core.Disposable subscription,
                                        Long runId, String workerId) {
        if (subscription != null && !subscription.isDisposed()) {
            subscription.dispose();
        }
        try {
            aiClient.cancelRequest(run.getRunUuid());
        } catch (Exception e) {
            log.debug("Best-effort cancel on timeout for run {} failed: {}", runId, e.getMessage());
        }

        inflightRuns.remove(runId, workerId);
        int affected = runMapper.completeRunGuarded(
                runId,
                AgentConstants.STATUS_TIMED_OUT,
                AgentConstants.ERR_EXECUTION_TIMEOUT,
                "执行超时：" + timeoutSeconds + " 秒",
                null,
                LocalDateTime.now());
        if (affected == 0) {
            log.info("Run {} timeout already converged by another path", runId);
            return;
        }

        AgentTask currentTask = taskMapper.selectById(run.getTaskId());
        if (currentTask == null) currentTask = task;
        if (currentTask != null && runId.equals(currentTask.getCurrentRunId())) {
            currentTask.setStatus(AgentConstants.STATUS_TIMED_OUT);
            taskMapper.updateById(currentTask);
        }
        statusEventService.record(run.getTaskId(), runId, "RUN_TIMED_OUT",
                AgentConstants.STATUS_TIMED_OUT,
                Map.of("timeoutSeconds", timeoutSeconds,
                        "runUuid", run.getRunUuid(),
                        "attemptNumber", run.getAttemptNumber()));
        if (currentTask != null) {
            handleTerminalFailure(currentTask, run,
                    AgentConstants.ERR_EXECUTION_TIMEOUT,
                    "执行超时：" + timeoutSeconds + " 秒");
        }
    }

    void handleTerminalFailure(AgentTask task, AgentRun run, String errorCode, String errorDetail) {
        if (retryPolicy.isRetryable(errorCode) && !retryPolicy.shouldDeadLetter(run.getAttemptNumber())) {
            scheduleNextAttempt(task);
        } else {
            String reason = "errorCode=" + errorCode + " attempt=" + run.getAttemptNumber()
                    + "/" + retryPolicy.getMaxAttempts();
            if (errorDetail != null && !errorDetail.isBlank()) {
                reason += " detail=" + (errorDetail.length() > 200 ? errorDetail.substring(0, 200) + "..." : errorDetail);
            }
            deadLetter(task, reason);
        }
    }

    @Override
    @Transactional
    public AgentRun scheduleNextAttempt(AgentTask task) {
        List<AgentRun> existingRuns = runMapper.selectByTaskId(task.getId());
        int attemptNumber = existingRuns.size() + 1;
        LocalDateTime scheduledAt = retryPolicy.computeNextScheduledAt(attemptNumber);
        long backoffSeconds = retryPolicy.backoffSeconds(attemptNumber);

        AgentRun newRun = new AgentRun();
        newRun.setTaskId(task.getId());
        newRun.setRunUuid(UUID.randomUUID().toString());
        newRun.setAttemptNumber(attemptNumber);
        newRun.setStatus(AgentConstants.STATUS_PENDING);
        newRun.setScheduledAt(scheduledAt);
        newRun.setDispatchCount(1);
        newRun.setModel(existingRuns.isEmpty() ? null : existingRuns.get(existingRuns.size() - 1).getModel());
        newRun.setStyle("detailed");
        newRun.setMaxToolSteps(5);
        runMapper.insert(newRun);

        // Update task: pending, point to new run
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(newRun.getId());
        taskMapper.updateById(task);

        // Record events
        statusEventService.record(task.getId(), newRun.getId(), "RETRY_SCHEDULED",
                AgentConstants.STATUS_PENDING,
                Map.of("attemptNumber", attemptNumber,
                        "scheduledAt", scheduledAt.toString(),
                        "backoffSeconds", backoffSeconds,
                        "previousRunId", task.getCurrentRunId() != null ? task.getCurrentRunId().toString() : ""));

        log.info("Scheduled retry for task {}: attempt={} backoff={}s scheduledAt={}",
                task.getId(), attemptNumber, backoffSeconds, scheduledAt);
        return newRun;
    }

    @Override
    @Transactional
    public void deadLetter(AgentTask task, String reason) {
        task.setStatus(AgentConstants.STATUS_DEAD_LETTER);
        task.setDeadLetterReason(reason);
        task.setDeadLetterAt(LocalDateTime.now());
        taskMapper.updateById(task);

        // Record events
        statusEventService.record(task.getId(), task.getCurrentRunId(), "DEAD_LETTERED",
                AgentConstants.STATUS_DEAD_LETTER,
                Map.of("reason", reason != null ? reason : ""));

        // Audit recovery event
        AgentRecoveryEvent auditEvent = new AgentRecoveryEvent();
        auditEvent.setRunId(task.getCurrentRunId() != null ? task.getCurrentRunId() : 0L);
        auditEvent.setTaskId(task.getId());
        auditEvent.setEventType("DEAD_LETTERED");
        auditEvent.setDetail(reason);
        recoveryEventMapper.insert(auditEvent);

        log.warn("Task {} moved to dead_letter: {}", task.getId(), reason);
    }

    @Override
    @Transactional
    public void markSuperseded(AgentRun run) {
        run.setStatus(AgentConstants.STATUS_FAILED);
        run.setErrorCode(AgentConstants.ERR_SUPERSEDED);
        run.setErrorDetail("被新的 Run 取代");
        run.setCompletedAt(LocalDateTime.now());
        run.setLeaseHolder(null);
        run.setLeaseExpiresAt(null);
        run.setHeartbeatAt(null);
        runMapper.updateById(run);

        // Audit recovery event
        AgentRecoveryEvent auditEvent = new AgentRecoveryEvent();
        auditEvent.setRunId(run.getId());
        auditEvent.setTaskId(run.getTaskId());
        auditEvent.setEventType("SUPERSEDED_REJECTED");
        auditEvent.setDetail("task.currentRunId points to a different run");
        recoveryEventMapper.insert(auditEvent);

        log.info("Run {} marked as superseded (taskId={})", run.getId(), run.getTaskId());
    }

    // ================================================================
    // 恢复扫描
    // ================================================================

    @Override
    public int recoverAll() {
        int recovered = 0;
        LocalDateTime now = LocalDateTime.now();

        // 1. Orphan detection: running runs with expired lease
        LocalDateTime staleBefore = now.minusSeconds(leaseSeconds);
        LocalDateTime timeoutBefore = now.minusSeconds(timeoutSeconds);
        List<AgentRun> orphaned = runMapper.selectLeaseExpiredRuns(staleBefore, batchSize * 2);
        for (AgentRun run : orphaned) {
            try {
                if (run.getStartedAt() != null && run.getStartedAt().isBefore(timeoutBefore)) {
                    // Watchdog timeout: run exceeded absolute timeout
                    runMapper.completeRunGuarded(run.getId(), AgentConstants.STATUS_TIMED_OUT,
                            AgentConstants.ERR_WATCHDOG_TIMEOUT,
                            "看门狗超时：租约过期且执行超过 " + timeoutSeconds + " 秒",
                            null, now);
                    AgentTask task = taskMapper.selectById(run.getTaskId());
                    if (task != null) {
                        handleTerminalFailure(task, run, AgentConstants.ERR_WATCHDOG_TIMEOUT,
                                "看门狗超时：租约过期且执行超过 " + timeoutSeconds + " 秒");
                    }
                    recordRecoveryAudit(run, "WATCHDOG_TIMED_OUT",
                            "lease expired + startedAt exceeded timeout " + timeoutSeconds + "s");
                    recovered++;
                } else {
                    // Orphan: lease expired but not yet timed out → reclaim
                    reclaimOrphan(run);
                    recovered++;
                }
            } catch (Exception e) {
                log.error("Error recovering orphaned run {}: {}", run.getId(), e.getMessage());
            }
        }

        // 2. Task convergence: tasks with terminal runs still marked running
        List<AgentTask> stuckTasks = taskMapper.selectList(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<AgentTask>()
                        .eq(AgentTask::getStatus, AgentConstants.STATUS_RUNNING));
        for (AgentTask task : stuckTasks) {
            try {
                if (task.getCurrentRunId() != null) {
                    AgentRun currentRun = runMapper.selectById(task.getCurrentRunId());
                    if (currentRun != null && AgentConstants.TERMINAL_STATUSES.contains(currentRun.getStatus())) {
                        task.setStatus(currentRun.getStatus());
                        taskMapper.updateById(task);
                        log.info("Converged task {} status {} → {} (aligned with run {})",
                                task.getId(), AgentConstants.STATUS_RUNNING, currentRun.getStatus(), currentRun.getId());
                    }
                }
            } catch (Exception e) {
                log.error("Error converging task {}: {}", task.getId(), e.getMessage());
            }
        }

        // 3. Dead-letter overdue: failed/timed_out tasks with attemptNumber >= maxAttempts
        List<AgentTask> overdueTasks = taskMapper.selectList(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<AgentTask>()
                        .in(AgentTask::getStatus, AgentConstants.RETRYABLE_STATUSES));
        for (AgentTask task : overdueTasks) {
            try {
                List<AgentRun> runs = runMapper.selectByTaskId(task.getId());
                if (!runs.isEmpty()) {
                    AgentRun lastRun = runs.get(runs.size() - 1);
                    if (retryPolicy.shouldDeadLetter(lastRun.getAttemptNumber())
                            && task.getDeadLetterAt() == null) {
                        deadLetter(task, "恢复扫描：已达最大尝试次数 " + retryPolicy.getMaxAttempts());
                    }
                }
            } catch (Exception e) {
                log.error("Error checking dead-letter overdue for task {}: {}", task.getId(), e.getMessage());
            }
        }

        if (recovered > 0) {
            log.info("Recovery scan: processed {} runs", recovered);
        }
        return recovered;
    }

    private void reclaimOrphan(AgentRun run) {
        // Check dispatch count limit
        if (run.getDispatchCount() >= retryPolicy.getMaxDispatchCount()) {
            log.warn("Run {} exhausted max dispatch count {} — treating as watchdog timeout",
                    run.getId(), run.getDispatchCount());
            runMapper.completeRunGuarded(run.getId(), AgentConstants.STATUS_TIMED_OUT,
                    AgentConstants.ERR_WATCHDOG_TIMEOUT,
                    "孤儿重派次数耗尽: dispatchCount=" + run.getDispatchCount(),
                    null, LocalDateTime.now());
            AgentTask task = taskMapper.selectById(run.getTaskId());
            if (task != null) {
                handleTerminalFailure(task, run, AgentConstants.ERR_WATCHDOG_TIMEOUT,
                        "孤儿重派次数耗尽: dispatchCount=" + run.getDispatchCount());
            }
            recordRecoveryAudit(run, "WATCHDOG_TIMED_OUT",
                    "max dispatch count " + retryPolicy.getMaxDispatchCount() + " reached");
            return;
        }

        // Best-effort cancel the orphaned Python task
        try {
            aiClient.cancelRequest(run.getRunUuid());
        } catch (Exception e) {
            log.debug("Best-effort cancel of orphaned Python task {} failed: {}", run.getRunUuid(), e.getMessage());
        }

        // Delete steps for idempotent re-execution
        stepMapper.deleteByRunId(run.getId());

        // Reset run: new UUID, pending, dispatch_count+1
        String newUuid = UUID.randomUUID().toString();
        LocalDateTime scheduledAt = LocalDateTime.now(); // immediate re-dispatch
        runMapper.requeueOrphan(run.getId(), newUuid, scheduledAt);

        recordRecoveryAudit(run, "ORPHAN_RECLAIMED",
                "new uuid=" + newUuid + " dispatchCount=" + (run.getDispatchCount() + 1));

        // Record recovery event
        statusEventService.record(run.getTaskId(), run.getId(), "RECOVERED",
                AgentConstants.STATUS_PENDING,
                Map.of("newRunUuid", newUuid, "dispatchCount", run.getDispatchCount() + 1));

        log.info("Orphan run {} reclaimed: new uuid={} dispatchCount={} taskId={}",
                run.getId(), newUuid, run.getDispatchCount() + 1, run.getTaskId());
    }

    private void convergeCancel(AgentRun run) {
        try {
            agentTaskService.cancelRun(run.getId());
            aiClient.cancelRequest(run.getRunUuid());
            redisUtils.delete(CANCEL_KEY_PREFIX + run.getId());
            statusEventService.record(run.getTaskId(), run.getId(), "CANCELLED",
                    AgentConstants.STATUS_CANCELLED, null);
            log.info("Run {} cancelled by worker (cancel flag detected)", run.getId());
        } catch (Exception e) {
            log.warn("Failed to converge cancel for run {}: {}", run.getId(), e.getMessage());
        }
    }

    // ================================================================
    // 心跳
    // ================================================================

    @Override
    public void heartbeatInFlightRuns() {
        for (Map.Entry<Long, String> entry : inflightRuns.entrySet()) {
            try {
                LocalDateTime now = LocalDateTime.now();
                runMapper.renewLease(entry.getKey(), entry.getValue(),
                        now.plusSeconds(leaseSeconds), now);
            } catch (Exception e) {
                log.warn("Heartbeat failed for run {}: {}", entry.getKey(), e.getMessage());
                inflightRuns.remove(entry.getKey());
            }
        }
    }

    // ================================================================
    // 取消检查
    // ================================================================

    @Override
    public boolean isRunCancelled(Long runId) {
        try {
            return redisUtils.hasKey(CANCEL_KEY_PREFIX + runId);
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * 设置 Run 取消标志（供外部调用，如 AgentTaskService.cancelTask）
     */
    public void setCancelFlag(Long runId) {
        try {
            redisUtils.set(CANCEL_KEY_PREFIX + runId, "1", cancelFlagTtlSeconds, TimeUnit.SECONDS);
            log.debug("Cancel flag set for run {}", runId);
        } catch (Exception e) {
            log.warn("Failed to set cancel flag for run {}: {}", runId, e.getMessage());
        }
    }

    // ================================================================
    // 辅助方法
    // ================================================================

    private String getWorkerId() {
        if (instanceId != null && !instanceId.isBlank()) {
            return instanceId;
        }
        String cached = generatedWorkerId;
        if (cached != null) return cached;
        synchronized (this) {
            if (generatedWorkerId == null) {
                try {
                    generatedWorkerId = java.net.InetAddress.getLocalHost().getHostName()
                            + "-" + UUID.randomUUID().toString().substring(0, 8);
                } catch (Exception e) {
                    generatedWorkerId = "worker-" + UUID.randomUUID().toString().substring(0, 8);
                }
            }
            return generatedWorkerId;
        }
    }

    private void recordRecoveryAudit(AgentRun run, String eventType, String detail) {
        try {
            AgentRecoveryEvent event = new AgentRecoveryEvent();
            event.setRunId(run.getId());
            event.setTaskId(run.getTaskId());
            event.setEventType(eventType);
            event.setDetail(detail);
            recoveryEventMapper.insert(event);
        } catch (Exception e) {
            log.warn("Failed to record recovery audit: {}", e.getMessage());
        }
    }
}
