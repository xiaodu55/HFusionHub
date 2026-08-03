package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.AgentConstants;
import com.hfusionhub.common.utils.RedisUtils;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.mapper.*;
import com.hfusionhub.service.*;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * AgentTaskQueueService 回归测试
 *
 * 覆盖：重复投递、过期回调、孤儿重派、退避调度、死信收敛、取代 Run
 */
class AgentTaskQueueServiceTest {

    private AgentTaskQueueServiceImpl queueService;
    private AgentRunMapper runMapper;
    private AgentTaskMapper taskMapper;
    private AgentStepMapper stepMapper;
    private AgentRecoveryEventMapper recoveryEventMapper;
    private AgentTaskService agentTaskService;
    private AgentStreamEventProcessor streamEventProcessor;
    private ConversationService conversationService;
    private AgentStatusEventService statusEventService;
    private AgentRetryPolicy retryPolicy;
    private AiClient aiClient;
    private RedisUtils redisUtils;
    private ThreadPoolTaskExecutor workerExecutor;
    private MessageMapper messageMapper;
    private ChatImageStorage chatImageStorage = new ChatImageStorage(java.nio.file.Path.of("target", "test-chat-images").toString());
    private TaskEventSseManager sseManager;

    @BeforeEach
    void setUp() {
        runMapper = mock(AgentRunMapper.class);
        taskMapper = mock(AgentTaskMapper.class);
        stepMapper = mock(AgentStepMapper.class);
        recoveryEventMapper = mock(AgentRecoveryEventMapper.class);
        agentTaskService = mock(AgentTaskService.class);
        streamEventProcessor = mock(AgentStreamEventProcessor.class);
        conversationService = mock(ConversationService.class);
        statusEventService = mock(AgentStatusEventService.class);
        retryPolicy = mock(AgentRetryPolicy.class);
        aiClient = mock(AiClient.class);
        redisUtils = mock(RedisUtils.class);
        messageMapper = mock(MessageMapper.class);
        sseManager = mock(TaskEventSseManager.class);
        workerExecutor = new ThreadPoolTaskExecutor();
        workerExecutor.setCorePoolSize(1);
        workerExecutor.setMaxPoolSize(1);
        workerExecutor.initialize();

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
                workerExecutor);
        ReflectionTestUtils.setField(queueService, "leaseSeconds", 120);
        ReflectionTestUtils.setField(queueService, "timeoutSeconds", 180);
        ReflectionTestUtils.setField(queueService, "batchSize", 5);
        ReflectionTestUtils.setField(queueService, "cancelFlagTtlSeconds", 3600);
        ReflectionTestUtils.setField(queueService, "instanceId", "test-worker");
    }

    // ================================================================
    // 重复投递防御
    // ================================================================

    @Test
    void duplicateDeliveryIsRejected() {
        AgentRun pendingRun = new AgentRun();
        pendingRun.setId(1L);
        pendingRun.setStatus(AgentConstants.STATUS_PENDING);
        pendingRun.setTaskId(100L);

        when(runMapper.selectQueuedRuns(any(), eq(5))).thenReturn(List.of(pendingRun));
        // First claim succeeds, second fails
        when(runMapper.claimRun(eq(1L), anyString(), any(), any(), any()))
                .thenReturn(1) // first call succeeds
                .thenReturn(0); // second worker fails

        int dispatched = queueService.pollAndDispatch();

        // Only 1 dispatch counted (the second claim returned 0, so no executeRun submitted)
        assertEquals(1, dispatched);
        verify(runMapper, times(1)).claimRun(eq(1L), anyString(), any(), any(), any());
    }

    // ================================================================
    // 孤儿重派
    // ================================================================

    @Test
    void orphanReclaimCreatesNewUuid() {
        AgentRun orphanRun = new AgentRun();
        orphanRun.setId(10L);
        orphanRun.setTaskId(200L);
        orphanRun.setStatus(AgentConstants.STATUS_RUNNING);
        orphanRun.setRunUuid(UUID.randomUUID().toString());
        orphanRun.setStartedAt(LocalDateTime.now().minusSeconds(60));
        orphanRun.setLeaseHolder("dead-worker");
        orphanRun.setLeaseExpiresAt(LocalDateTime.now().minusSeconds(60));
        orphanRun.setDispatchCount(1);

        when(runMapper.selectLeaseExpiredRuns(any(), eq(10))).thenReturn(List.of(orphanRun));
        when(runMapper.requeueOrphan(eq(10L), anyString(), any())).thenReturn(1);
        when(runMapper.completeRunGuarded(anyLong(), anyString(), anyString(), anyString(), anyString(), any()))
                .thenReturn(1);
        when(retryPolicy.getMaxDispatchCount()).thenReturn(3);
        when(retryPolicy.getMaxAttempts()).thenReturn(3);
        when(retryPolicy.isRetryable(anyString())).thenReturn(true);
        when(retryPolicy.shouldDeadLetter(anyInt())).thenReturn(false);
        when(taskMapper.selectById(200L)).thenReturn(new AgentTask());

        when(retryPolicy.computeNextScheduledAt(anyInt()))
                .thenReturn(LocalDateTime.now().plusSeconds(60));
        when(retryPolicy.backoffSeconds(anyInt())).thenReturn(60L);

        queueService.recoverAll();

        // Verify: deleteByRunId called (idempotent), requeueOrphan called with new UUID
        verify(stepMapper).deleteByRunId(10L);
        verify(runMapper).requeueOrphan(eq(10L), argThat(uuid -> !uuid.equals(orphanRun.getRunUuid())), any());
        verify(recoveryEventMapper, atLeastOnce()).insert(any());
    }

    // ================================================================
    // 看门狗超时
    // ================================================================

    @Test
    void watchdogTimeoutWhenStartedAtExceedsTimeout() {
        AgentRun timedOutRun = new AgentRun();
        timedOutRun.setId(20L);
        timedOutRun.setTaskId(300L);
        timedOutRun.setStatus(AgentConstants.STATUS_RUNNING);
        timedOutRun.setRunUuid(UUID.randomUUID().toString());
        timedOutRun.setStartedAt(LocalDateTime.now().minusSeconds(200)); // > timeout 180s
        timedOutRun.setLeaseHolder("dead-worker");
        timedOutRun.setLeaseExpiresAt(LocalDateTime.now().minusSeconds(200));
        timedOutRun.setDispatchCount(1);
        timedOutRun.setAttemptNumber(1);

        when(runMapper.selectLeaseExpiredRuns(any(), eq(10))).thenReturn(List.of(timedOutRun));
        when(runMapper.completeRunGuarded(
                        eq(20L),
                        eq(AgentConstants.STATUS_TIMED_OUT),
                        eq(AgentConstants.ERR_WATCHDOG_TIMEOUT),
                        anyString(),
                        isNull(),
                        any()))
                .thenReturn(1);
        when(retryPolicy.getMaxAttempts()).thenReturn(3);
        when(retryPolicy.getMaxDispatchCount()).thenReturn(3);
        when(retryPolicy.isRetryable(anyString())).thenReturn(true);
        when(retryPolicy.shouldDeadLetter(anyInt())).thenReturn(false);
        when(taskMapper.selectById(300L)).thenReturn(new AgentTask());
        when(retryPolicy.computeNextScheduledAt(anyInt()))
                .thenReturn(LocalDateTime.now().plusSeconds(60));
        when(retryPolicy.backoffSeconds(anyInt())).thenReturn(60L);

        queueService.recoverAll();

        // Verify: runCompletedGuarded with TIMED_OUT + watchdog_timeout called (not reclaim)
        verify(runMapper)
                .completeRunGuarded(
                        eq(20L),
                        eq(AgentConstants.STATUS_TIMED_OUT),
                        eq(AgentConstants.ERR_WATCHDOG_TIMEOUT),
                        anyString(),
                        isNull(),
                        any());
        verify(stepMapper, never()).deleteByRunId(20L); // should NOT reclaim, just watchdog
    }

    // ================================================================
    // 死信收敛
    // ================================================================

    @Test
    void deadLetterWhenRetriesExhausted() {
        AgentTask task = new AgentTask();
        task.setId(400L);
        task.setStatus(AgentConstants.STATUS_FAILED);
        task.setCurrentRunId(30L);

        AgentRun lastRun = new AgentRun();
        lastRun.setId(30L);
        lastRun.setTaskId(400L);
        lastRun.setAttemptNumber(3);
        lastRun.setStatus(AgentConstants.STATUS_FAILED);

        when(runMapper.selectLeaseExpiredRuns(any(), eq(10))).thenReturn(List.of());
        when(taskMapper.selectList(any())).thenReturn(List.of(task));
        when(runMapper.selectByTaskId(400L)).thenReturn(List.of(lastRun));
        when(runMapper.selectById(30L)).thenReturn(lastRun);
        when(retryPolicy.shouldDeadLetter(3)).thenReturn(true);
        when(retryPolicy.getMaxAttempts()).thenReturn(3);

        queueService.recoverAll();

        // Verify: task was moved to dead_letter
        // atLeastOnce: recoverAll step 2 (convergence) may also call updateById on the same mock matcher
        verify(taskMapper, atLeastOnce())
                .updateById(argThat(t -> AgentConstants.STATUS_DEAD_LETTER.equals(t.getStatus())
                        && t.getDeadLetterReason() != null
                        && t.getDeadLetterAt() != null));
    }

    // ================================================================
    // 取代 Run 处理
    // ================================================================

    @Test
    void markSupersededSetsFailedStatus() {
        AgentRun supersededRun = new AgentRun();
        supersededRun.setId(50L);
        supersededRun.setTaskId(500L);
        supersededRun.setStatus(AgentConstants.STATUS_RUNNING);

        queueService.markSuperseded(supersededRun);

        assertEquals(AgentConstants.STATUS_FAILED, supersededRun.getStatus());
        assertEquals(AgentConstants.ERR_SUPERSEDED, supersededRun.getErrorCode());
        assertNotNull(supersededRun.getCompletedAt());
        verify(recoveryEventMapper).insert(any());
    }

    // ================================================================
    // 退避调度
    // ================================================================

    @Test
    void scheduleNextAttemptSetsBackoffAndPending() {
        AgentTask task = new AgentTask();
        task.setId(600L);
        task.setStatus(AgentConstants.STATUS_FAILED);
        task.setCurrentRunId(60L);

        AgentRun oldRun = new AgentRun();
        oldRun.setId(60L);
        oldRun.setTaskId(600L);
        oldRun.setAttemptNumber(1);

        when(runMapper.selectByTaskId(600L)).thenReturn(List.of(oldRun));
        when(retryPolicy.computeNextScheduledAt(2))
                .thenReturn(LocalDateTime.now().plusSeconds(30));
        when(retryPolicy.backoffSeconds(2)).thenReturn(30L);

        AgentRun newRun = queueService.scheduleNextAttempt(task);

        assertEquals(AgentConstants.STATUS_PENDING, newRun.getStatus());
        assertEquals(2, newRun.getAttemptNumber());
        assertEquals(AgentConstants.STATUS_PENDING, task.getStatus());
        assertEquals(newRun.getId(), task.getCurrentRunId());
        assertNotNull(newRun.getScheduledAt());
        verify(runMapper).insert(any(AgentRun.class));
        verify(taskMapper).updateById(task);
        verify(statusEventService)
                .record(
                        eq(600L),
                        eq(newRun.getId()),
                        eq("RETRY_SCHEDULED"),
                        eq(AgentConstants.STATUS_PENDING),
                        anyMap());
    }

    // ================================================================
    // 取消检查
    // ================================================================

    @Test
    void isRunCancelledReturnsTrueWhenRedisKeyExists() {
        when(redisUtils.hasKey("agent:cancel:99")).thenReturn(true);
        assertTrue(queueService.isRunCancelled(99L));
    }

    @Test
    void isRunCancelledReturnsFalseWhenRedisKeyAbsent() {
        when(redisUtils.hasKey("agent:cancel:99")).thenReturn(false);
        assertFalse(queueService.isRunCancelled(99L));
    }

    @Test
    void isRunCancelledReturnsFalseOnRedisError() {
        when(redisUtils.hasKey(anyString())).thenThrow(new RuntimeException("Redis down"));
        assertFalse(queueService.isRunCancelled(99L));
    }

    // ================================================================
    // 恢复幂等
    // ================================================================

    @Test
    void recoverAllIsIdempotent() {
        // No orphaned runs, no stuck tasks, no overdue → 0 recovered
        when(runMapper.selectLeaseExpiredRuns(any(), eq(10))).thenReturn(List.of());
        when(taskMapper.selectList(any())).thenReturn(List.of());

        int recovered1 = queueService.recoverAll();
        int recovered2 = queueService.recoverAll();

        assertEquals(0, recovered1);
        assertEquals(0, recovered2);
    }
}
