package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.mapper.*;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.*;
import com.hfusionhub.tenant.TenantContext;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * Agent 队列端到端集成测试：入队 → Worker 同步执行 → 状态事件 → 完成/取消。
 * 使用 SyncTaskExecutor 使 Worker 执行在线程内同步完成，避免竞态。
 */
class AgentTaskQueueIntegrationTest {

    private AgentTaskQueueServiceImpl queueService;
    private AgentTaskServiceImpl agentTaskService;
    private AgentRunMapper runMapper;
    private AgentTaskMapper taskMapper;
    private AgentStepMapper stepMapper;
    private AgentRecoveryEventMapper recoveryEventMapper;
    private AgentStreamEventProcessor streamEventProcessor;
    private ConversationService conversationService;
    private AgentStatusEventService statusEventService;
    private AgentRetryPolicy retryPolicy;
    private AiClient aiClient;
    private MessageMapper messageMapper;
    private ChatImageStorage chatImageStorage = new ChatImageStorage(java.nio.file.Path.of("target", "test-chat-images").toString());
    private TaskEventSseManager sseManager;
    private com.hfusionhub.common.utils.RedisUtils redisUtils;
    private com.hfusionhub.service.UsageLedgerService usageLedgerService;
    private com.hfusionhub.config.QuotaProperties quotaProperties;

    @BeforeEach
    void setUp() {
        runMapper = mock(AgentRunMapper.class);
        taskMapper = mock(AgentTaskMapper.class);
        stepMapper = mock(AgentStepMapper.class);
        recoveryEventMapper = mock(AgentRecoveryEventMapper.class);
        streamEventProcessor = mock(AgentStreamEventProcessor.class);
        conversationService = mock(ConversationService.class);
        statusEventService = mock(AgentStatusEventService.class);
        retryPolicy = mock(AgentRetryPolicy.class);
        aiClient = mock(AiClient.class);
        messageMapper = mock(MessageMapper.class);
        sseManager = mock(TaskEventSseManager.class);
        redisUtils = mock(com.hfusionhub.common.utils.RedisUtils.class);

        // Use SyncTaskExecutor so executeRun completes synchronously in pollAndDispatch
        SyncTaskExecutor syncExecutor = new SyncTaskExecutor();

        // Real AgentTaskServiceImpl
        AgentApprovalMapper approvalMapper = mock(AgentApprovalMapper.class);
        AgentTaskQueueService queueServiceRef = mock(AgentTaskQueueService.class);
        usageLedgerService = mock(com.hfusionhub.service.UsageLedgerService.class);
        quotaProperties = mock(com.hfusionhub.config.QuotaProperties.class);
        when(quotaProperties.getChatMaxOutputTokens()).thenReturn(8192L);
        agentTaskService = new AgentTaskServiceImpl(
                taskMapper,
                runMapper,
                stepMapper,
                approvalMapper,
                messageMapper,
                mock(com.hfusionhub.mapper.UserMapper.class),
                aiClient,
                queueServiceRef,
                statusEventService,
                redisUtils,
                usageLedgerService,
                quotaProperties,
                mock(com.hfusionhub.service.CostTrackingService.class),
                new AgentRunLifecycleService(
                        runMapper,
                        taskMapper,
                        mock(com.hfusionhub.mapper.UserMapper.class),
                        usageLedgerService));
        ReflectionTestUtils.setField(agentTaskService, "leaseSeconds", 120);
        ReflectionTestUtils.setField(agentTaskService, "cancelFlagTtlSeconds", 3600);

        queueService = new AgentTaskQueueServiceImpl(
                taskMapper,
                runMapper,
                stepMapper,
                recoveryEventMapper,
                agentTaskService,
                streamEventProcessor,
                conversationService,
                statusEventService,
                retryPolicy,
                aiClient,
                redisUtils,
                messageMapper,
                chatImageStorage,
                sseManager,
                syncExecutor);
        ReflectionTestUtils.setField(queueService, "leaseSeconds", 120);
        ReflectionTestUtils.setField(queueService, "timeoutSeconds", 180);
        ReflectionTestUtils.setField(queueService, "batchSize", 5);
        ReflectionTestUtils.setField(queueService, "cancelFlagTtlSeconds", 3600);
        ReflectionTestUtils.setField(queueService, "instanceId", "test-worker");

        // Default retry config
        when(retryPolicy.getMaxAttempts()).thenReturn(3);
        when(retryPolicy.getMaxDispatchCount()).thenReturn(3);
        when(retryPolicy.isRetryable(anyString())).thenReturn(false);
        when(retryPolicy.shouldDeadLetter(anyInt())).thenReturn(false);
    }

    // ================================================================
    // 入队 → 状态事件
    // ================================================================

    @Test
    void enqueueRunCreatesPendingRunAndRecordsQueuedEvent() {
        AgentTask task = new AgentTask();
        task.setId(100L);
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setRequestId("req-100");
        task.setUserId(1L);
        task.setConversationId(10L);

        when(taskMapper.selectByIdForUpdate(100L)).thenReturn(task);
        when(runMapper.selectByTaskId(100L)).thenReturn(List.of());
        when(runMapper.insert(any(AgentRun.class))).thenAnswer(inv -> {
            AgentRun r = inv.getArgument(0);
            r.setId(200L);
            return 1;
        });
        when(taskMapper.updateById(any(AgentTask.class))).thenReturn(1);

        AgentRun run = agentTaskService.enqueueRun(100L);

        assertNotNull(run);
        assertEquals(AgentConstants.STATUS_PENDING, run.getStatus());
        assertEquals(1, run.getAttemptNumber());
        assertNotNull(run.getScheduledAt());
        assertNotNull(run.getRunUuid());

        // QUEUED event recorded
        verify(statusEventService)
                .record(
                        eq(100L),
                        eq(200L),
                        eq("QUEUED"),
                        eq(AgentConstants.STATUS_PENDING),
                        argThat(payload -> payload.containsKey("attemptNumber") && payload.containsKey("runUuid")));

        // Task updated: PENDING, currentRunId set
        verify(taskMapper)
                .updateById(argThat(
                        t -> AgentConstants.STATUS_PENDING.equals(t.getStatus()) && t.getCurrentRunId() != null));
    }

    @Test
    void enqueueRunFromRetryableStatusSucceeds() {
        AgentTask task = new AgentTask();
        task.setId(200L);
        task.setStatus(AgentConstants.STATUS_FAILED);
        task.setRequestId("req-200");
        task.setUserId(1L);

        when(taskMapper.selectByIdForUpdate(200L)).thenReturn(task);
        when(runMapper.selectByTaskId(200L)).thenReturn(List.of());
        when(runMapper.insert(any(AgentRun.class))).thenAnswer(inv -> {
            AgentRun r = inv.getArgument(0);
            r.setId(300L);
            return 1;
        });
        when(taskMapper.updateById(any(AgentTask.class))).thenReturn(1);

        AgentRun run = agentTaskService.enqueueRun(200L);
        assertEquals(AgentConstants.STATUS_PENDING, run.getStatus());
    }

    @Test
    void enqueueRunFromTerminalStatusThrows() {
        AgentTask task = new AgentTask();
        task.setId(300L);
        task.setStatus(AgentConstants.STATUS_SUCCEEDED);
        when(taskMapper.selectByIdForUpdate(300L)).thenReturn(task);

        assertThrows(com.hfusionhub.common.exception.BusinessException.class, () -> agentTaskService.enqueueRun(300L));
    }

    // ================================================================
    // V77/S4: attempt 计算 + 唯一索引并发守卫
    // ================================================================

    @Test
    void enqueueRunComputesAttemptFromMaxAttemptNumber() {
        AgentTask task = new AgentTask();
        task.setId(210L);
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setRequestId("req-210");
        task.setUserId(1L);

        when(taskMapper.selectByIdForUpdate(210L)).thenReturn(task);
        when(runMapper.selectByTaskId(210L)).thenReturn(List.of());
        when(runMapper.selectMaxAttemptNumber(210L)).thenReturn(3);
        when(runMapper.insert(any(AgentRun.class))).thenAnswer(inv -> {
            AgentRun r = inv.getArgument(0);
            r.setId(310L);
            return 1;
        });
        when(taskMapper.updateById(any(AgentTask.class))).thenReturn(1);

        AgentRun run = agentTaskService.enqueueRun(210L);

        assertEquals(4, run.getAttemptNumber());
    }

    @Test
    void enqueueRunRejectsDuplicateAttemptOnConcurrentInsert() {
        AgentTask task = new AgentTask();
        task.setId(220L);
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setRequestId("req-220");
        task.setUserId(1L);

        when(taskMapper.selectByIdForUpdate(220L)).thenReturn(task);
        when(runMapper.selectByTaskId(220L)).thenReturn(List.of());
        when(runMapper.selectMaxAttemptNumber(220L)).thenReturn(0);
        when(runMapper.insert(any(AgentRun.class)))
                .thenThrow(new org.springframework.dao.DuplicateKeyException("uk_run_task_attempt"));

        // V77 唯一索引 (task_id, attempt_number) 冲突 → 友好冲突错误，不记录事件
        assertThrows(com.hfusionhub.common.exception.BusinessException.class, () -> agentTaskService.enqueueRun(220L));
        verify(statusEventService, never()).record(anyLong(), anyLong(), anyString(), anyString(), anyMap());
    }

    // ================================================================
    // Worker 派发 → 同步执行 → 内容广播 + 消息保存
    // ================================================================

    @Test
    void workerProcessesContentChunksAndBroadcastsToSse() {
        AgentTask task = new AgentTask();
        task.setId(500L);
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(50L);
        task.setUserId(1L);
        task.setConversationId(50L);
        task.setQuery("test query");
        task.setRequestId("req-500");

        AgentRun pendingRun = buildClaimedRun(50L, 500L);

        when(runMapper.selectQueuedRuns(any(), eq(5))).thenReturn(List.of(pendingRun));
        when(runMapper.claimRun(eq(50L), eq("test-worker"), any(), any(), any()))
                .thenReturn(1);
        when(runMapper.selectById(50L)).thenReturn(pendingRun);
        when(runMapper.releaseLease(eq(50L), anyString())).thenReturn(1);
        when(taskMapper.selectById(500L)).thenReturn(task);
        when(conversationService.getChatHistory(50L)).thenReturn(List.of());
        when(redisUtils.hasKey(anyString())).thenReturn(false);

        // Simulate non-KB stream: content + [DONE]
        reactor.core.publisher.Flux<String> contentFlux = reactor.core.publisher.Flux.just(
                "data: {\"content\":\"Hello\"}", "data: {\"content\":\" World\"}", "data: [DONE]");
        when(aiClient.streamChat(
                        eq("test query"), eq(50L), isNull(), anyList(), eq(pendingRun.getRunUuid()), anyLong(), any(), any()))
                .thenReturn(contentFlux);

        // Act — SyncTaskExecutor makes executeRun complete within pollAndDispatch
        int dispatched = queueService.pollAndDispatch();
        assertEquals(1, dispatched);

        // Content broadcast to SSE
        verify(sseManager).broadcastContentChunk(eq(500L), eq("Hello"));
        verify(sseManager).broadcastContentChunk(eq(500L), eq(" World"));
        verify(sseManager).broadcastDone(500L);

        // Assistant message saved with accumulated content
        ArgumentCaptor<com.hfusionhub.entity.Message> msgCaptor =
                ArgumentCaptor.forClass(com.hfusionhub.entity.Message.class);
        verify(messageMapper).insert(msgCaptor.capture());
        com.hfusionhub.entity.Message saved = msgCaptor.getValue();
        assertEquals("assistant", saved.getRole());
        assertEquals("Hello World", saved.getContent());
        assertEquals(50L, saved.getConversationId());
        assertEquals("req-500:assistant", saved.getRequestId());
    }

    @Test
    void workerRejectsUnresolvableTenantBeforeCallingAi() {
        AgentTask task = new AgentTask();
        task.setId(560L);
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(56L);
        task.setQuery("must not execute without a tenant");
        // userId intentionally absent: run -> task -> owner cannot resolve.

        AgentRun run = buildClaimedRun(56L, 560L);
        run.setTenantId(null);

        when(runMapper.selectQueuedRuns(any(), eq(5))).thenReturn(List.of(run));
        when(runMapper.claimRun(eq(56L), eq("test-worker"), any(), any(), any()))
                .thenReturn(1);
        when(runMapper.selectById(56L)).thenReturn(run);
        when(runMapper.releaseLease(eq(56L), anyString())).thenReturn(1);
        when(taskMapper.selectById(560L)).thenReturn(task);
        when(redisUtils.hasKey(anyString())).thenReturn(false);
        when(runMapper.completeRunGuarded(
                        eq(56L),
                        eq(AgentConstants.STATUS_FAILED),
                        eq("tenant_unresolvable"),
                        anyString(),
                        isNull(),
                        any()))
                .thenReturn(1);
        when(taskMapper.updateById(any(AgentTask.class))).thenReturn(1);

        assertEquals(1, queueService.pollAndDispatch());

        verify(aiClient, never()).streamChat(anyString(), any(), any(), any(), anyString(), any(), any());
        verify(aiClient, never()).agentV1ChatStream(anyString(), any(), any(), any(), anyString(), any(), any());
        verify(runMapper)
                .completeRunGuarded(
                        eq(56L),
                        eq(AgentConstants.STATUS_FAILED),
                        eq("tenant_unresolvable"),
                        anyString(),
                        isNull(),
                        any());
    }

    @Test
    void workerBroadcastsSourcesToSse() {
        AgentTask task = new AgentTask();
        task.setId(510L);
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(51L);
        task.setUserId(1L);
        task.setConversationId(51L);
        task.setQuery("query with sources");
        task.setRequestId("req-510");

        AgentRun pendingRun = buildClaimedRun(51L, 510L);

        when(runMapper.selectQueuedRuns(any(), eq(5))).thenReturn(List.of(pendingRun));
        when(runMapper.claimRun(eq(51L), eq("test-worker"), any(), any(), any()))
                .thenReturn(1);
        when(runMapper.selectById(51L)).thenReturn(pendingRun);
        when(runMapper.releaseLease(eq(51L), anyString())).thenReturn(1);
        when(taskMapper.selectById(510L)).thenReturn(task);
        when(conversationService.getChatHistory(51L)).thenReturn(List.of());
        when(redisUtils.hasKey(anyString())).thenReturn(false);

        String sourcesJson = "data: {\"sources\":[{\"title\":\"doc1.pdf\",\"page\":3}]}";
        reactor.core.publisher.Flux<String> flux = reactor.core.publisher.Flux.just(sourcesJson, "data: [DONE]");
        when(aiClient.streamChat(anyString(), anyLong(), isNull(), anyList(), anyString(), anyLong(), any(), any()))
                .thenReturn(flux);

        queueService.pollAndDispatch();

        verify(sseManager).broadcastSources(eq(510L), anyList());
        verify(sseManager).broadcastDone(510L);
    }

    @Test
    void workerTimesOutAndSchedulesRetryWhenPythonStreamNeverEnds() {
        AgentTask task = new AgentTask();
        task.setId(540L);
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(54L);
        task.setUserId(1L);
        task.setQuery("stuck query");
        task.setRequestId("req-540");

        AgentRun run = buildClaimedRun(54L, 540L);
        when(runMapper.selectQueuedRuns(any(), eq(5))).thenReturn(List.of(run));
        when(runMapper.claimRun(eq(54L), eq("test-worker"), any(), any(), any()))
                .thenReturn(1);
        when(runMapper.selectById(54L)).thenReturn(run);
        when(runMapper.selectByTaskId(540L)).thenReturn(List.of(run));
        when(runMapper.completeRunGuarded(
                        eq(54L),
                        eq(AgentConstants.STATUS_TIMED_OUT),
                        eq(AgentConstants.ERR_EXECUTION_TIMEOUT),
                        anyString(),
                        isNull(),
                        any()))
                .thenReturn(1);
        when(runMapper.releaseLease(eq(54L), anyString())).thenReturn(0);
        when(runMapper.insert(any(AgentRun.class))).thenAnswer(invocation -> {
            AgentRun retry = invocation.getArgument(0);
            retry.setId(55L);
            return 1;
        });
        when(taskMapper.selectById(540L)).thenReturn(task);
        when(taskMapper.updateById(any(AgentTask.class))).thenReturn(1);
        when(redisUtils.hasKey(anyString())).thenReturn(false);
        when(aiClient.cancelRequest(anyString())).thenReturn(true);
        when(retryPolicy.isRetryable(AgentConstants.ERR_EXECUTION_TIMEOUT)).thenReturn(true);
        when(retryPolicy.shouldDeadLetter(1)).thenReturn(false);
        when(retryPolicy.computeNextScheduledAt(2))
                .thenReturn(LocalDateTime.now().plusSeconds(1));
        when(retryPolicy.backoffSeconds(2)).thenReturn(1L);

        ReflectionTestUtils.setField(queueService, "timeoutSeconds", 1);
        reactor.core.publisher.Flux<String> neverEnding = reactor.core.publisher.Flux.just(
                        "data: {\"content\":\"partial\"}")
                .concatWith(reactor.core.publisher.Flux.never());
        when(aiClient.streamChat(
                        eq("stuck query"), isNull(), isNull(), anyList(), eq(run.getRunUuid()), anyLong(), any(), any()))
                .thenReturn(neverEnding);

        assertEquals(1, queueService.pollAndDispatch());

        verify(aiClient, atLeastOnce()).cancelRequest(run.getRunUuid());
        verify(runMapper)
                .completeRunGuarded(
                        eq(54L),
                        eq(AgentConstants.STATUS_TIMED_OUT),
                        eq(AgentConstants.ERR_EXECUTION_TIMEOUT),
                        anyString(),
                        isNull(),
                        any());
        verify(statusEventService)
                .record(eq(540L), eq(54L), eq("RUN_TIMED_OUT"), eq(AgentConstants.STATUS_TIMED_OUT), anyMap());
        verify(statusEventService)
                .record(eq(540L), eq(55L), eq("RETRY_SCHEDULED"), eq(AgentConstants.STATUS_PENDING), anyMap());
        verify(sseManager, never()).broadcastDone(540L);
    }

    @Test
    void workerHandlesKbBoundTaskViaV1Endpoint() {
        AgentTask task = new AgentTask();
        task.setId(520L);
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(52L);
        task.setUserId(1L);
        task.setConversationId(52L);
        task.setKnowledgeBaseId(5L); // KB-bound!
        task.setQuery("kb query");
        task.setRequestId("req-520");

        AgentRun pendingRun = buildClaimedRun(52L, 520L);

        when(runMapper.selectQueuedRuns(any(), eq(5))).thenReturn(List.of(pendingRun));
        when(runMapper.claimRun(eq(52L), eq("test-worker"), any(), any(), any()))
                .thenReturn(1);
        when(runMapper.selectById(52L)).thenReturn(pendingRun);
        when(runMapper.releaseLease(eq(52L), anyString())).thenReturn(1);
        when(taskMapper.selectById(520L)).thenReturn(task);
        when(conversationService.getChatHistory(52L)).thenReturn(List.of());
        when(redisUtils.hasKey(anyString())).thenReturn(false);

        // V1 endpoint returns structured events
        reactor.core.publisher.Flux<String> v1Flux = reactor.core.publisher.Flux.just(
                "data: {\"event\":\"step_completed\",\"data\":{}}", "data: {\"event\":\"run_completed\",\"data\":{}}");
        when(aiClient.agentV1ChatStream(
                        eq("kb query"), eq(52L), eq(5L), anyList(), eq(pendingRun.getRunUuid()), eq(1L), isNull(), any(), any()))
                .thenReturn(v1Flux);

        queueService.pollAndDispatch();

        // Structured events processed through streamEventProcessor
        verify(streamEventProcessor, times(2)).handleLine(anyString(), eq(52L));
        verify(sseManager).broadcastDone(520L);
    }

    @Test
    void workerAbortsWhenCancelledMidStream() {
        AgentTask task = new AgentTask();
        task.setId(530L);
        task.setStatus(AgentConstants.STATUS_PENDING);
        task.setCurrentRunId(53L);
        task.setUserId(1L);
        task.setConversationId(53L);
        task.setQuery("query to cancel");
        task.setRequestId("req-530");

        AgentRun claimedRun = buildClaimedRun(53L, 530L);

        when(runMapper.selectQueuedRuns(any(), eq(5))).thenReturn(List.of(claimedRun));
        when(runMapper.claimRun(eq(53L), eq("test-worker"), any(), any(), any()))
                .thenReturn(1);
        when(runMapper.selectById(53L)).thenReturn(claimedRun);
        when(runMapper.releaseLease(eq(53L), anyString())).thenReturn(1);
        when(taskMapper.selectById(530L)).thenReturn(task);
        when(conversationService.getChatHistory(53L)).thenReturn(List.of());
        // cancelRun → completeRun → completeRunGuarded
        when(runMapper.completeRunGuarded(
                        eq(53L), eq(AgentConstants.STATUS_CANCELLED), anyString(), anyString(), isNull(), any()))
                .thenReturn(1);
        when(taskMapper.updateById(any(AgentTask.class))).thenReturn(1);
        // Cancel flag becomes true during stream processing (second check)
        when(redisUtils.hasKey("agent:cancel:53")).thenReturn(false, true);
        when(redisUtils.delete(anyString())).thenReturn(true);

        reactor.core.publisher.Flux<String> flux =
                reactor.core.publisher.Flux.just("data: {\"content\":\"Hello\"}", "data: {\"content\":\" World\"}");
        when(aiClient.streamChat(anyString(), anyLong(), isNull(), anyList(), anyString(), anyLong(), any(), any()))
                .thenReturn(flux);
        when(aiClient.cancelRequest(anyString())).thenReturn(true);

        queueService.pollAndDispatch();

        // Redis cancel key cleaned up by convergeCancel (may be called twice due to both chunks)
        verify(redisUtils, atLeastOnce()).delete("agent:cancel:53");
        // Run was completed as cancelled (guarded write is idempotent)
        verify(runMapper, atLeastOnce())
                .completeRunGuarded(
                        eq(53L), eq(AgentConstants.STATUS_CANCELLED), anyString(), anyString(), isNull(), any());
    }

    // ================================================================
    // 死信验证
    // ================================================================

    @Test
    void deadLetterWhenRetriesExhaustedAndRecoverScans() {
        AgentTask task = new AgentTask();
        task.setId(600L);
        task.setStatus(AgentConstants.STATUS_FAILED);
        task.setCurrentRunId(60L);

        AgentRun lastRun = new AgentRun();
        lastRun.setId(60L);
        lastRun.setTaskId(600L);
        lastRun.setAttemptNumber(3);
        lastRun.setStatus(AgentConstants.STATUS_FAILED);

        when(runMapper.selectLeaseExpiredRuns(any(), eq(10))).thenReturn(List.of());
        when(taskMapper.selectList(any())).thenReturn(List.of(task));
        when(runMapper.selectByTaskId(600L)).thenReturn(List.of(lastRun));
        when(runMapper.selectById(60L)).thenReturn(lastRun);
        when(retryPolicy.shouldDeadLetter(3)).thenReturn(true);

        queueService.recoverAll();

        verify(taskMapper, atLeastOnce())
                .updateById(argThat(t -> AgentConstants.STATUS_DEAD_LETTER.equals(t.getStatus())
                        && t.getDeadLetterReason() != null
                        && t.getDeadLetterAt() != null));
    }

    // ================================================================
    // AGENT_TOKENS 用量账本
    // ================================================================

    @Test
    void startRunReservesAgentTokensKeyedByRunUuid() {
        TenantContext.setTenantId(1L);
        try {
            AgentTask task = new AgentTask();
            task.setId(700L);
            task.setStatus(AgentConstants.STATUS_PENDING);
            task.setRequestId("req-700");
            task.setUserId(1L);
            task.setQuery("如何部署HFusionHub？");
            task.setConversationId(10L);

            AgentRun inserted = new AgentRun();
            inserted.setId(7001L);
            inserted.setTenantId(1L);

            when(taskMapper.selectById(700L)).thenReturn(task);
            when(runMapper.selectByTaskId(700L)).thenReturn(List.of());
            when(runMapper.insert(any(AgentRun.class))).thenAnswer(inv -> {
                AgentRun r = inv.getArgument(0);
                r.setId(7001L);
                return 1;
            });
            // startRun 内部 reserve 会再查一次 run（拿 runUuid / tenantId）
            when(runMapper.selectById(7001L)).thenAnswer(inv -> {
                AgentRun copy = new AgentRun();
                copy.setId(7001L);
                copy.setTaskId(700L);
                copy.setTenantId(1L);
                copy.setRunUuid("uuid-7001");
                return copy;
            });
            when(taskMapper.updateById(any(AgentTask.class))).thenReturn(1);

            agentTaskService.startRun(700L, "uuid-7001", "deepseek", "detailed", 5);

            // reserve 量 = 输入估算(64) + 8192 × (5+1) = 49216，幂等键 agent_run:uuid-7001
            verify(usageLedgerService)
                    .reserve(
                            eq(UsageMeter.AGENT_TOKENS),
                            eq("agent_run:uuid-7001"),
                            eq(49216L),
                            eq("agent_run"),
                            eq("7001"));
        } finally {
            TenantContext.clear();
        }
    }

    @Test
    void completeRunSucceedsSettlesWithActualTokens() {
        TenantContext.setTenantId(1L);
        try {
            AgentRun run = new AgentRun();
            run.setId(8001L);
            run.setTaskId(800L);
            run.setTenantId(1L);
            run.setRunUuid("uuid-8001");
            run.setStatus(AgentConstants.STATUS_RUNNING);
            run.setStartedAt(LocalDateTime.now());

            when(runMapper.selectById(8001L)).thenReturn(run);
            when(runMapper.completeRunGuarded(eq(8001L), anyString(), any(), any(), any(), any()))
                    .thenReturn(1);
            when(taskMapper.selectById(800L)).thenReturn(null);

            agentTaskService.completeRun(
                    8001L,
                    AgentConstants.STATUS_SUCCEEDED,
                    "deepseek",
                    Map.of("prompt_tokens", 100, "completion_tokens", 40, "total_tokens", 140),
                    3,
                    500,
                    null,
                    null,
                    null);

            verify(usageLedgerService)
                    .settle(
                            eq(UsageMeter.AGENT_TOKENS),
                            eq("agent_run:uuid-8001"),
                            eq(140L),
                            eq("agent_run"),
                            eq("8001"));
            verify(runMapper)
                    .updateCompletionMetadata(
                            eq(8001L),
                            eq("deepseek"),
                            eq(Map.of("prompt_tokens", 100, "completion_tokens", 40, "total_tokens", 140)),
                            eq(3),
                            eq(500L));
        } finally {
            TenantContext.clear();
        }
    }

    @Test
    void completeRunFailureReleasesReservation() {
        TenantContext.setTenantId(1L);
        try {
            AgentRun run = new AgentRun();
            run.setId(8002L);
            run.setTaskId(801L);
            run.setTenantId(1L);
            run.setRunUuid("uuid-8002");
            run.setStatus(AgentConstants.STATUS_RUNNING);
            run.setStartedAt(LocalDateTime.now());

            when(runMapper.selectById(8002L)).thenReturn(run);
            when(runMapper.completeRunGuarded(eq(8002L), anyString(), any(), any(), any(), any()))
                    .thenReturn(1);
            when(taskMapper.selectById(801L)).thenReturn(null);

            agentTaskService.completeRun(
                    8002L, AgentConstants.STATUS_FAILED, "deepseek", null, 0, 500, "internal_error", "boom", null);

            verify(usageLedgerService).release(eq(UsageMeter.AGENT_TOKENS), eq("agent_run:uuid-8002"));
        } finally {
            TenantContext.clear();
        }
    }

    @Test
    void recoveryWatchdogTimeoutReleasesReservation() {
        TenantContext.setTenantId(1L);
        try {
            AgentRun run = new AgentRun();
            run.setId(10001L);
            run.setTaskId(1000L);
            run.setTenantId(1L);
            run.setRunUuid("uuid-10001");
            run.setStatus(AgentConstants.STATUS_RUNNING);
            run.setStartedAt(LocalDateTime.now().minusSeconds(200));
            run.setLeaseExpiresAt(LocalDateTime.now().minusSeconds(10));

            when(runMapper.selectLeaseExpiredRuns(any(), eq(10))).thenReturn(List.of(run));
            when(runMapper.completeRunGuarded(
                            eq(10001L), eq(AgentConstants.STATUS_TIMED_OUT), any(), any(), any(), any()))
                    .thenReturn(1);
            when(runMapper.selectById(10001L)).thenReturn(run);
            when(taskMapper.selectById(1000L)).thenReturn(null);

            queueService.recoverAll();

            verify(usageLedgerService).release(eq(UsageMeter.AGENT_TOKENS), eq("agent_run:uuid-10001"));
        } finally {
            TenantContext.clear();
        }
    }

    // ── helpers ──

    /**
     * Build a run that has ALREADY been claimed (status=RUNNING with lease).
     * executeRun re-reads the run after claim, so status must be RUNNING.
     */
    private AgentRun buildClaimedRun(Long runId, Long taskId) {
        AgentRun run = new AgentRun();
        run.setId(runId);
        run.setTaskId(taskId);
        run.setTenantId(1L);
        run.setStatus(AgentConstants.STATUS_RUNNING); // claimed → running
        run.setRunUuid(UUID.randomUUID().toString());
        run.setScheduledAt(LocalDateTime.now());
        run.setDispatchCount(1);
        run.setAttemptNumber(1);
        run.setLeaseHolder("test-worker");
        run.setLeaseExpiresAt(LocalDateTime.now().plusSeconds(120));
        run.setStartedAt(LocalDateTime.now());
        return run;
    }
}
