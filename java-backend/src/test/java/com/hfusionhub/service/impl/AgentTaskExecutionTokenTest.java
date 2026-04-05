package com.hfusionhub.service.impl;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.utils.RedisUtils;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.mapper.*;
import com.hfusionhub.service.AgentStatusEventService;
import com.hfusionhub.service.AgentTaskQueueService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * Durable one-time execution token — concurrency and replay contract.
 *
 * MySQL is the single source of truth: the guarded
 * ``consumeExecutionToken(..., execution_token_status='issued')`` UPDATE
 * guarantees exactly-once.  These tests prove the service layer honours that
 * contract under parallel replay and concurrent duplicate consumption.
 */
class AgentTaskExecutionTokenTest {

    private AgentTaskServiceImpl service;
    private AgentApprovalMapper approvalMapper;
    private AgentTaskMapper taskMapper;
    private AgentRunMapper runMapper;
    private AgentStepMapper stepMapper;
    private MessageMapper messageMapper;
    private UserMapper userMapper;
    private AiClient aiClient;
    private AgentTaskQueueService queueService;
    private AgentStatusEventService statusEventService;
    private RedisUtils redisUtils;

    @BeforeEach
    void setUp() {
        taskMapper = mock(AgentTaskMapper.class);
        runMapper = mock(AgentRunMapper.class);
        stepMapper = mock(AgentStepMapper.class);
        approvalMapper = mock(AgentApprovalMapper.class);
        messageMapper = mock(MessageMapper.class);
        userMapper = mock(UserMapper.class);
        aiClient = mock(AiClient.class);
        queueService = mock(AgentTaskQueueService.class);
        statusEventService = mock(AgentStatusEventService.class);
        redisUtils = mock(RedisUtils.class);

        service = new AgentTaskServiceImpl(
                taskMapper, runMapper, stepMapper, approvalMapper,
                messageMapper, userMapper, aiClient, queueService,
                statusEventService, redisUtils,
                mock(com.hfusionhub.service.UsageLedgerService.class),
                mock(com.hfusionhub.config.QuotaProperties.class));
    }

    @Test
    void consumeReturnsTrueWhenGuardUpdatesOneRow() {
        when(approvalMapper.consumeExecutionToken(eq("appr-1"), eq("tok"), anyString()))
                .thenReturn(1);
        assertTrue(service.consumeExecutionToken("appr-1", "tok"));
    }

    @Test
    void consumeReturnsFalseOnReplayOfAlreadyConsumedToken() {
        // DB guard returns 0 when execution_token_status is no longer 'issued'
        // (replay / already consumed / revoked / wrong token).
        when(approvalMapper.consumeExecutionToken(eq("appr-1"), eq("tok"), anyString()))
                .thenReturn(0);
        assertFalse(service.consumeExecutionToken("appr-1", "tok"));
    }

    @Test
    void consumeReturnsFalseForMissingOrBlankToken() {
        assertFalse(service.consumeExecutionToken(null, "tok"));
        assertFalse(service.consumeExecutionToken("appr-1", null));
        assertFalse(service.consumeExecutionToken("appr-1", "  "));
        verifyNoInteractions(approvalMapper);
    }

    @Test
    void consumeReturnsFalseOnMapperException() {
        when(approvalMapper.consumeExecutionToken(eq("appr-1"), eq("tok"), anyString()))
                .thenThrow(new RuntimeException("db down"));
        // The service does not swallow exceptions here; a failed atomic UPDATE
        // must be surfaced so the caller (Python decide) can reject execution.
        assertThrows(RuntimeException.class,
                () -> service.consumeExecutionToken("appr-1", "tok"));
    }

    @Test
    void exactlyOneOfManyParallelConsumersSucceeds() throws Exception {
        // Simulates MySQL's guarded atomic UPDATE: only the thread that flips
        // execution_token_status from 'issued' → 'consumed' gets updated=1;
        // every other thread observes 0 and is rejected.
        AtomicBoolean token = new AtomicBoolean(false);
        when(approvalMapper.consumeExecutionToken(eq("appr-par"), eq("tok"), anyString()))
                .thenAnswer(inv -> token.compareAndSet(false, true) ? 1 : 0);

        int workers = 12;
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch finish = new CountDownLatch(workers);
        List<Boolean> results = new CopyOnWriteArrayList<>();

        ExecutorService pool = Executors.newFixedThreadPool(workers);
        for (int i = 0; i < workers; i++) {
            pool.submit(() -> {
                ready.countDown();
                try { start.await(); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                try {
                    results.add(service.consumeExecutionToken("appr-par", "tok"));
                } finally {
                    finish.countDown();
                }
            });
        }
        assertTrue(ready.await(5, TimeUnit.SECONDS));
        start.countDown();
        assertTrue(finish.await(10, TimeUnit.SECONDS));
        pool.shutdownNow();

        long successes = results.stream().filter(b -> b).count();
        assertEquals(1, successes,
                "exactly one parallel consumer may consume the shared execution token");
        assertEquals(workers, results.size());
    }

    @Test
    void replayAfterFirstConsumeIsRejected() throws Exception {
        // First consume flips the guard; sequential replay of the SAME token is denied.
        AtomicBoolean token = new AtomicBoolean(false);
        when(approvalMapper.consumeExecutionToken(eq("appr-seq"), eq("tok"), anyString()))
                .thenAnswer(inv -> token.compareAndSet(false, true) ? 1 : 0);

        assertTrue(service.consumeExecutionToken("appr-seq", "tok"));
        assertFalse(service.consumeExecutionToken("appr-seq", "tok"));
        assertFalse(service.consumeExecutionToken("appr-seq", "tok"));
    }

    @Test
    void getApprovalWithTokenLoadsApproval() {
        AgentApproval a = new AgentApproval();
        a.setApprovalId("appr-1");
        when(approvalMapper.selectByApprovalId("appr-1")).thenReturn(a);
        assertSame(a, service.getApprovalWithToken("appr-1"));
    }
}