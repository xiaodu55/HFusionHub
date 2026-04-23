package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.hfusionhub.dto.GateResult;
import com.hfusionhub.entity.AgentEvaluationDataset;
import com.hfusionhub.entity.AgentEvaluationRun;
import com.hfusionhub.entity.EvaluationGateResult;
import com.hfusionhub.entity.ModelUsageRecord;
import com.hfusionhub.entity.WebhookDelivery;
import com.hfusionhub.entity.WebhookSubscription;
import com.hfusionhub.mapper.AgentEvaluationDatasetMapper;
import com.hfusionhub.mapper.AgentEvaluationRunMapper;
import com.hfusionhub.mapper.EvaluationGateResultMapper;
import com.hfusionhub.mapper.ModelUsageRecordMapper;
import com.hfusionhub.mapper.WebhookDeliveryMapper;
import com.hfusionhub.mapper.WebhookSubscriptionMapper;
import com.hfusionhub.service.CostTrackingService;
import com.hfusionhub.service.EvaluationGateService;
import com.hfusionhub.service.WebhookSubscriptionService;
import com.hfusionhub.tenant.TenantContext;
import com.hfusionhub.webhook.WebhookEventPublisher;
import com.hfusionhub.webhook.WebhookEventTypes;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ActiveProfiles;

/**
 * 三个新能力模块（成本追踪 / Webhook / 评测回归门禁）集成冒烟测试（H2）。
 * 覆盖：成本落账与按日/汇总统计、Webhook 订阅 CRUD 与事件异步分发投递、
 * 评测门禁判定（准确率/延迟/成本基线）与历史持久化。
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("test")
class CostWebhookGateIntegrationTest {

    /** 投递到不可达地址，投递必然失败但流程完整走通 */
    private static final String UNREACHABLE_URL = "http://127.0.0.1:1/unreachable-webhook";

    @MockBean
    private StringRedisTemplate stringRedisTemplate;

    @MockBean
    private RedisConnectionFactory redisConnectionFactory;

    @Autowired
    private CostTrackingService costTrackingService;

    @Autowired
    private WebhookSubscriptionService webhookSubscriptionService;

    @Autowired
    private EvaluationGateService evaluationGateService;

    @Autowired
    private WebhookEventPublisher webhookEventPublisher;

    @Autowired
    private ModelUsageRecordMapper modelUsageRecordMapper;

    @Autowired
    private WebhookSubscriptionMapper webhookSubscriptionMapper;

    @Autowired
    private WebhookDeliveryMapper webhookDeliveryMapper;

    @Autowired
    private AgentEvaluationDatasetMapper datasetMapper;

    @Autowired
    private AgentEvaluationRunMapper runMapper;

    @Autowired
    private EvaluationGateResultMapper gateResultMapper;

    @BeforeEach
    void setUp() {
        modelUsageRecordMapper.delete(Wrappers.emptyWrapper());
        webhookDeliveryMapper.delete(Wrappers.emptyWrapper());
        webhookSubscriptionMapper.delete(Wrappers.emptyWrapper());
        gateResultMapper.delete(Wrappers.emptyWrapper());
        runMapper.delete(Wrappers.emptyWrapper());
        datasetMapper.delete(Wrappers.emptyWrapper());
        TenantContext.setTenantId(1L);
    }

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    // ================================================================
    // 1. 成本追踪
    // ================================================================

    @Test
    void costTracking_recordAndSummaries() {
        recordUsage(1L, "gpt-4o", 100, 50, 1.234567, 800, "chat");
        recordUsage(1L, "gpt-4o", 200, 80, 2.000000, 1200, "agent");

        var daily = costTrackingService.getUserDailyCost(1L, 30);
        assertFalse(daily.isEmpty(), "应有每日成本记录");
        assertTrue(daily.get(0).getTotalTokens() >= 430, "每日 tokens 应累加");
        assertTrue(daily.get(0).getTotalCost().compareTo(BigDecimal.valueOf(3.23)) >= 0, "每日成本应累加");

        var summary = costTrackingService.getCostSummary(1L);
        assertEquals(1L, summary.getUserId());
        assertTrue(summary.getTotalRequests() >= 2);
        assertTrue(summary.getTotalCost().compareTo(BigDecimal.valueOf(3.23)) >= 0);
        assertNotNull(summary.getEstimatedMonthCost(), "应有本月预估成本");
        assertFalse(summary.getModelBreakdown().isEmpty(), "应有按模型分组明细");
        assertEquals("gpt-4o", summary.getModelBreakdown().get(0).getModel());

        var tenantSummary = costTrackingService.getTenantCostSummary(1L, null, null);
        assertTrue(tenantSummary.getTotalRequests() >= 2, "租户汇总应统计到记录");
        assertTrue(tenantSummary.getModelBreakdown().size() >= 1);
    }

    // ================================================================
    // 2. Webhook 系统
    // ================================================================

    @Test
    void webhook_subscriptionCrudAndTestFire() {
        WebhookSubscription sub = new WebhookSubscription();
        sub.setName("评测通知");
        sub.setUrl(UNREACHABLE_URL);
        sub.setEvents(List.of(WebhookEventTypes.EVALUATION_COMPLETED, WebhookEventTypes.AGENT_TASK_COMPLETED));

        WebhookSubscription created = webhookSubscriptionService.create(1L, sub);
        assertNotNull(created.getId(), "创建应返回 ID");
        assertNotNull(created.getSecret(), "未提供密钥时应自动生成");
        assertEquals(2, created.getEvents().size());
        assertEquals(1, created.getIsActive());
        assertEquals(1L, created.getTenantId());

        // 读取往返：JSON 事件列表应正确反序列化
        WebhookSubscription loaded = webhookSubscriptionService.get(1L, created.getId());
        assertTrue(loaded.getEvents().contains(WebhookEventTypes.EVALUATION_COMPLETED));

        // 更新
        loaded.setName("改名后的订阅");
        webhookSubscriptionService.update(1L, created.getId(), loaded);
        assertEquals(
                "改名后的订阅", webhookSubscriptionService.get(1L, created.getId()).getName());

        // 停用
        webhookSubscriptionService.setActive(1L, created.getId(), false);
        assertEquals(0, webhookSubscriptionService.get(1L, created.getId()).getIsActive());
        webhookSubscriptionService.setActive(1L, created.getId(), true);

        // 测试触发：不可达地址 → 失败投递但记录落库
        WebhookDelivery delivery = webhookSubscriptionService.testFire(1L, created.getId());
        assertEquals(0, delivery.getSuccess(), "不可达地址投递应失败");
        assertNotNull(delivery.getResponseStatus());

        // 投递历史
        var history = webhookSubscriptionService.deliveryHistory(1L, created.getId(), 1, 20);
        assertTrue(history.getTotal() >= 1, "应有投递历史");

        // 归属校验
        org.junit.jupiter.api.Assertions.assertThrows(
                RuntimeException.class, () -> webhookSubscriptionService.get(999L, created.getId()));

        // 逻辑删除
        webhookSubscriptionService.delete(1L, created.getId());
        org.junit.jupiter.api.Assertions.assertThrows(
                RuntimeException.class, () -> webhookSubscriptionService.get(1L, created.getId()));
    }

    @Test
    void webhook_eventDispatchToMatchingSubscription() throws InterruptedException {
        WebhookSubscription sub = new WebhookSubscription();
        sub.setName("评测事件订阅");
        sub.setUrl(UNREACHABLE_URL);
        sub.setEvents(List.of(WebhookEventTypes.EVALUATION_COMPLETED));
        WebhookSubscription created = webhookSubscriptionService.create(1L, sub);

        // 发布不匹配事件 → 不应触发投递
        webhookEventPublisher.publish(WebhookEventTypes.DOCUMENT_INDEXED, 1L, 1L, Map.of());
        Thread.sleep(500);
        assertEquals(0L, countDeliveries(created.getId(), WebhookEventTypes.DOCUMENT_INDEXED), "未订阅的事件不应触发投递");

        // 发布匹配事件 → 异步分发投递（失败但留下记录），连续失败计数 +1
        webhookEventPublisher.publish(
                WebhookEventTypes.EVALUATION_COMPLETED, 1L, 1L, Map.of("datasetId", 1L, "passed", true));
        waitFor(() -> countDeliveries(created.getId(), WebhookEventTypes.EVALUATION_COMPLETED) >= 1, 10_000);
        waitFor(
                () -> {
                    WebhookSubscription after = webhookSubscriptionMapper.selectById(created.getId());
                    return after != null && after.getFailureCount() != null && after.getFailureCount() >= 1;
                },
                10_000);
    }

    // ================================================================
    // 3. 评测回归门禁
    // ================================================================

    @Test
    void evaluationGate_passAndFailAgainstBaseline() {
        Long datasetId = insertDataset("门禁测试集", 1L);

        // 基线评测：成本 0.010000
        Long baselineRunId =
                insertRun(datasetId, "completed", 0.85, Map.of("latency_p95", 1200.0, "token_cost", 0.010000));
        // 本次评测：准确率高、延迟低、成本不超基线 1.2 倍 → 通过
        Long passRunId = insertRun(datasetId, "completed", 0.92, Map.of("latency_p95", 900.0, "token_cost", 0.011000));

        GateResult passed = evaluationGateService.checkGate(1L, datasetId, passRunId);
        assertTrue(passed.isPassed(), "成本未超基线 1.2 倍应通过门禁");
        assertNotNull(passed.getBaselineRunUuid(), "应识别出基线评测");

        // 本次评测成本 0.02 >= 基线 0.01 × 1.2 → 成本项失败
        Long failRunId = insertRun(datasetId, "completed", 0.95, Map.of("latency_p95", 500.0, "token_cost", 0.020000));
        GateResult failed = evaluationGateService.checkGate(1L, datasetId, failRunId);
        assertFalse(failed.isPassed(), "成本超基线应未通过门禁");
        assertNotNull(failed.getCriteria());
        assertTrue(failed.getCriteria().stream()
                .anyMatch(c -> "token_cost".equals(c.getName()) && "FAILED".equals(c.getStatus())));

        // 延迟超 5000ms → 延迟项失败
        Long latencyFailRunId =
                insertRun(datasetId, "completed", 0.99, Map.of("latency_p95", 6000.0, "token_cost", 0.005000));
        GateResult latencyFailed = evaluationGateService.checkGate(1L, datasetId, latencyFailRunId);
        assertFalse(latencyFailed.isPassed(), "延迟超 5000ms 应未通过门禁");
        assertTrue(latencyFailed.getCriteria().stream()
                .anyMatch(c -> "latency_p95".equals(c.getName()) && "FAILED".equals(c.getStatus())));

        // 未完成评测 → 门禁不通过
        Long runningRunId = insertRun(datasetId, "running", null, Map.of());
        GateResult blocked = evaluationGateService.checkGate(1L, datasetId, runningRunId);
        assertFalse(blocked.isPassed(), "未完成评测不应通过门禁");

        // 门禁历史
        List<EvaluationGateResult> history = evaluationGateService.gateHistory(1L, datasetId, 1, 20);
        assertTrue(history.size() >= 4, "应持久化 4 条门禁结果，实际: " + history.size());
    }

    // ================================================================
    // 辅助
    // ================================================================

    private void recordUsage(
            Long userId, String model, int prompt, int completion, double costUsd, int latencyMs, String requestType) {
        ModelUsageRecord record = new ModelUsageRecord();
        record.setUserId(userId);
        record.setTenantId(1L);
        record.setModel(model);
        record.setProvider("openai");
        record.setPromptTokens(prompt);
        record.setCompletionTokens(completion);
        record.setCostUsd(BigDecimal.valueOf(costUsd));
        record.setLatencyMs(latencyMs);
        record.setRequestType(requestType);
        costTrackingService.record(record);
    }

    private Long insertDataset(String name, Long userId) {
        AgentEvaluationDataset dataset = new AgentEvaluationDataset();
        dataset.setName(name);
        dataset.setUserId(userId);
        dataset.setCaseCount(0);
        datasetMapper.insert(dataset);
        return dataset.getId();
    }

    private Long insertRun(Long datasetId, String status, Double score, Map<String, Object> summary) {
        AgentEvaluationRun run = new AgentEvaluationRun();
        run.setDatasetId(datasetId);
        run.setRunUuid("run-" + System.nanoTime());
        run.setStatus(status);
        run.setOverallScore(score);
        run.setCaseResults(Map.of("summary", summary));
        runMapper.insert(run);
        return run.getId();
    }

    private long countDeliveries(Long subscriptionId, String eventType) {
        LambdaQueryWrapper<WebhookDelivery> query = new LambdaQueryWrapper<>();
        query.eq(WebhookDelivery::getSubscriptionId, subscriptionId).eq(WebhookDelivery::getEventType, eventType);
        return webhookDeliveryMapper.selectCount(query);
    }

    private void waitFor(CheckedBoolean condition, long timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            if (condition.get()) {
                return;
            }
            Thread.sleep(200);
        }
        org.junit.jupiter.api.Assertions.fail("等待条件超时（" + timeoutMs + "ms）");
    }

    @FunctionalInterface
    private interface CheckedBoolean {
        boolean get() throws InterruptedException;
    }
}
