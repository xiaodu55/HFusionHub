package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.hfusionhub.support.AbstractItMySQLTest;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.TenantQuota;
import com.hfusionhub.entity.UsageCounter;
import com.hfusionhub.entity.UsageReservation;
import com.hfusionhub.mapper.TenantQuotaMapper;
import com.hfusionhub.mapper.UsageCounterMapper;
import com.hfusionhub.mapper.UsageEventMapper;
import com.hfusionhub.mapper.UsageReservationMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 用量账本核心集成测试（H2，真实 MyBatis-Plus mapper 栈）。
 * 覆盖：预占/结算/退回、幂等、超额结算封顶、终态互斥、跨日窗口结算、
 * 跨租户相同 requestId 隔离、无租户上下文 fail-closed、并发重复预占。
 */
class UsageLedgerServiceImplTest extends AbstractItMySQLTest {

    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @MockBean
    private RedisConnectionFactory redisConnectionFactory;

    @Autowired
    private UsageLedgerService usageLedgerService;

    @Autowired
    private TenantQuotaMapper tenantQuotaMapper;

    @Autowired
    private UsageReservationMapper usageReservationMapper;

    @Autowired
    private UsageCounterMapper usageCounterMapper;

    @Autowired
    private UsageEventMapper usageEventMapper;

    @BeforeEach
    void setUp() {
        // 共享 H2 在单 JVM 内跨测试方法持久；并发/独立线程用例会提交。
        // 每用例前清空账本表，保证配额累计与断言自洽。
        usageEventMapper.delete(Wrappers.emptyWrapper());
        usageReservationMapper.delete(Wrappers.emptyWrapper());
        usageCounterMapper.delete(Wrappers.emptyWrapper());
        tenantQuotaMapper.delete(Wrappers.emptyWrapper());
        TenantContext.setTenantId(1L);
    }

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    @Test
    void reserveThenSettleMovesReservationToCommitted() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:test-1", 500, "message", "test-1");

        assertEquals(500, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
        assertEquals(0, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
        assertEquals(500, usageLedgerService.currentUsage(UsageMeter.CHAT_TOKENS));

        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, "chat:test-1", 400, "message", "test-1");

        assertEquals(0, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
        assertEquals(400, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
        assertEquals(400, usageLedgerService.currentUsage(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void releaseReturnsReservation() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:test-2", 300, "message", "test-2");
        assertEquals(300, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));

        usageLedgerService.release(UsageMeter.CHAT_TOKENS, "chat:test-2");

        assertEquals(0, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
        assertEquals(0, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void reserveIsIdempotentForSameRequestId() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:test-3", 200, "message", "test-3");
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:test-3", 200, "message", "test-3");

        assertEquals(200, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void settleAndReleaseAreIdempotentForSameRequestId() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:test-4", 100, "message", "test-4");
        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, "chat:test-4", 80, "message", "test-4");
        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, "chat:test-4", 80, "message", "test-4");

        assertEquals(80, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));

        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:test-5", 100, "message", "test-5");
        usageLedgerService.release(UsageMeter.CHAT_TOKENS, "chat:test-5");
        usageLedgerService.release(UsageMeter.CHAT_TOKENS, "chat:test-5");

        assertEquals(0, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void settleCapsAtReservedWhenActualExceedsReservation() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:over-reserve", 100, "message", "over-reserve");

        // 实际用量 500 远超预占 100：结算量封顶为 100，reserved 归零且不为负
        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, "chat:over-reserve", 500, "message", "over-reserve");

        assertEquals(100, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
        assertEquals(0, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
        assertEquals(100, usageLedgerService.currentUsage(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void commitThenReleaseDoesNotDoubleRelease() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:tx-1", 100, "message", "tx-1");
        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, "chat:tx-1", 100, "message", "tx-1");
        assertEquals(100, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));

        // COMMIT 后再 RELEASE：禁止，reserved 不得再被扣减
        usageLedgerService.release(UsageMeter.CHAT_TOKENS, "chat:tx-1");

        assertEquals(100, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
        assertEquals(0, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void releaseThenCommitDoesNotDoubleCommit() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:tx-2", 100, "message", "tx-2");
        usageLedgerService.release(UsageMeter.CHAT_TOKENS, "chat:tx-2");
        assertEquals(0, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));

        // RELEASE 后再 COMMIT：禁止，不得把已退回的预留重新结算
        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, "chat:tx-2", 100, "message", "tx-2");

        assertEquals(0, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
        assertEquals(0, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void settleUsesReservationWindowKeyAcrossMidnight() {
        // 模拟前一日 23:59 的预占（reservation + counter 均在旧窗口）
        UsageReservation old = new UsageReservation();
        old.setTenantId(1L);
        old.setMeter(UsageMeter.CHAT_TOKENS.getCode());
        old.setRequestId("chat:oldday");
        old.setWindowKey("2000-01-01");
        old.setReservedAmount(1000L);
        old.setActualAmount(0L);
        old.setState(UsageReservation.STATE_RESERVED);
        usageReservationMapper.insert(old);

        UsageCounter oldCounter = new UsageCounter();
        oldCounter.setTenantId(1L);
        oldCounter.setMeter(UsageMeter.CHAT_TOKENS.getCode());
        oldCounter.setWindowKey("2000-01-01");
        oldCounter.setReserved(1000L);
        oldCounter.setCommitted(0L);
        usageCounterMapper.insert(oldCounter);

        // 跨零点后在“今天”结算：应作用于预占所在旧窗口
        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, "chat:oldday", 800, "message", "oldday");

        UsageCounter after = usageCounterMapper.selectByKey(1L, UsageMeter.CHAT_TOKENS.getCode(), "2000-01-01");
        assertEquals(800L, after.getCommitted());
        // settle 释放完整预占：reserved 1000 - 1000 = 0
        assertEquals(0L, after.getReserved());
        // 今天窗口不受影响
        assertEquals(0L, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
        assertEquals(0L, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void sameRequestIdAcrossTenantsIsIsolated() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:same-id", 50, "message", "t1");
        TenantContext.runAs(2L, () -> {
            usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:same-id", 80, "message", "t2");
            return null;
        });

        assertEquals(50L, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
        TenantContext.runAs(2L, () -> {
            assertEquals(80L, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
            return null;
        });
    }

    @Test
    void noTenantContextFailsClosed() {
        TenantContext.clear();
        assertThrows(IllegalStateException.class, () -> usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
        assertThrows(
                IllegalStateException.class,
                () -> usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:nctx", 10, "message", "nctx"));
    }

    @Test
    void runAsRestoresContextFromContextlessThread() throws Exception {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:thread", 100, "message", "thread");

        // 模拟 Reactor 线程：无租户上下文，必须 runAs 恢复后才可结算
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CountDownLatch done = new CountDownLatch(1);
            pool.submit(() -> {
                try {
                    TenantContext.runAs(1L, () -> {
                        usageLedgerService.settle(UsageMeter.CHAT_TOKENS, "chat:thread", 90, "message", "thread");
                        return null;
                    });
                } finally {
                    done.countDown();
                }
            });
            assertTrue(done.await(10, TimeUnit.SECONDS), "settle on contextless thread timed out");
        } finally {
            pool.shutdownNow();
        }

        assertEquals(90L, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
        // settle 释放完整预占：reserved 100 - 100 = 0
        assertEquals(0L, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void reserveOverLimitThrowsQuotaExceededAndRollsBack() {
        long limit = usageLedgerService.effectiveDailyLimit(UsageMeter.CHAT_TOKENS);
        assertTrue(limit >= 100000);

        BusinessException ex = assertThrows(
                BusinessException.class,
                () -> usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:over", limit + 1, "message", "over"));
        assertEquals(StatusCode.QUOTA_EXCEEDED, ex.getCode());

        assertEquals(0, usageLedgerService.currentUsage(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void cumulativeReservesHitTheLimit() {
        long limit = usageLedgerService.effectiveDailyLimit(UsageMeter.CHAT_TOKENS);
        long half = limit / 2;
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:a", half, "message", "a");
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:b", half, "message", "b");

        BusinessException ex = assertThrows(
                BusinessException.class,
                () -> usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:c", 1, "message", "c"));
        assertEquals(StatusCode.QUOTA_EXCEEDED, ex.getCode());
        assertEquals(limit, usageLedgerService.currentUsage(UsageMeter.CHAT_TOKENS));
    }

    @Test
    void tenantQuotaOverrideWinsOverPlanDefault() {
        TenantQuota quota = new TenantQuota();
        quota.setTenantId(1L);
        quota.setMeter(UsageMeter.CHAT_TOKENS.getCode());
        quota.setDailyLimit(42L);
        tenantQuotaMapper.insert(quota);

        assertEquals(42L, usageLedgerService.effectiveDailyLimit(UsageMeter.CHAT_TOKENS));

        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:override", 42, "message", "override");
        BusinessException ex = assertThrows(
                BusinessException.class,
                () -> usageLedgerService.reserve(
                        UsageMeter.CHAT_TOKENS, "chat:override-2", 1, "message", "override-2"));
        assertEquals(StatusCode.QUOTA_EXCEEDED, ex.getCode());
    }

    @Test
    void metersAreIsolated() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:iso", 50, "message", "iso");
        assertEquals(50, usageLedgerService.currentUsage(UsageMeter.CHAT_TOKENS));
        assertEquals(0, usageLedgerService.currentUsage(UsageMeter.AGENT_TOKENS));
        assertEquals(0, usageLedgerService.currentUsage(UsageMeter.INDEX_CHUNKS));
        assertEquals(0, usageLedgerService.currentUsage(UsageMeter.PLUGIN_EXECUTIONS));
    }

    @Test
    void zeroAmountReserveIsIgnored() {
        usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:zero", 0, "message", "zero");
        assertEquals(0, usageLedgerService.currentUsage(UsageMeter.CHAT_TOKENS));
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void concurrentDuplicateReserveIsIdempotent() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(4);
        try {
            for (int i = 0; i < 4; i++) {
                pool.submit(() -> {
                    try {
                        start.await();
                        TenantContext.runAs(1L, () -> {
                            usageLedgerService.reserve(UsageMeter.CHAT_TOKENS, "chat:race", 100, "message", "race");
                            return null;
                        });
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        done.countDown();
                    }
                });
            }
            start.countDown();
            assertTrue(done.await(15, TimeUnit.SECONDS), "concurrent reserve timed out");
        } finally {
            pool.shutdownNow();
        }

        // 4 个线程同一 requestId 预占，只应预占一次
        assertEquals(100L, usageLedgerService.currentReserved(UsageMeter.CHAT_TOKENS));
        assertEquals(0L, usageLedgerService.currentCommitted(UsageMeter.CHAT_TOKENS));
    }
}
