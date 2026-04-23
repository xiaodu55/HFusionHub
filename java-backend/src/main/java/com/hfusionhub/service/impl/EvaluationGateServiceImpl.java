package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.GateCriterion;
import com.hfusionhub.dto.GateResult;
import com.hfusionhub.entity.AgentEvaluationDataset;
import com.hfusionhub.entity.AgentEvaluationRun;
import com.hfusionhub.entity.EvaluationGateResult;
import com.hfusionhub.mapper.AgentEvaluationDatasetMapper;
import com.hfusionhub.mapper.AgentEvaluationRunMapper;
import com.hfusionhub.mapper.EvaluationGateResultMapper;
import com.hfusionhub.service.EvaluationGateService;
import com.hfusionhub.tenant.TenantContext;
import com.hfusionhub.webhook.WebhookEventPublisher;
import com.hfusionhub.webhook.WebhookEventTypes;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 评测回归门禁服务实现
 *
 * <p>门禁规则（全部门槛同时满足才放行）：</p>
 * <ul>
 *   <li>accuracy &gt; 0.80</li>
 *   <li>latency_p95 &lt; 5000ms</li>
 *   <li>token_cost &lt; 基线 token 成本 × 1.2（基线为同数据集最近一次 completed 的评测）</li>
 * </ul>
 *
 * <p>延迟与成本指标从评测执行记录的 {@code caseResults.summary} 中读取
 * （Python 评测服务上报），未上报的指标记为 SKIPPED、不参与门禁判定。
 * 门禁结果持久化到 {@code evaluation_gate_result}，并通过
 * {@link WebhookEventPublisher} 发布 {@code evaluation.completed} 事件。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class EvaluationGateServiceImpl implements EvaluationGateService {

    /** 准确率门槛（必须严格大于） */
    private static final double ACCURACY_THRESHOLD = 0.80;

    /** P95 延迟门槛（毫秒，必须严格小于） */
    private static final double LATENCY_P95_MAX_MS = 5000.0;

    /** 成本门槛：本次成本必须小于基线成本 × 该系数 */
    private static final double COST_BASELINE_RATIO = 1.2;

    /** caseResults.summary 中延迟字段的候选键 */
    private static final String[] LATENCY_KEYS = {"latency_p95", "latency_p95_ms", "p95_latency_ms"};
    /** caseResults.summary 中成本字段的候选键 */
    private static final String[] COST_KEYS = {"token_cost", "cost_usd", "total_cost_usd"};

    private final AgentEvaluationDatasetMapper datasetMapper;
    private final AgentEvaluationRunMapper runMapper;
    private final EvaluationGateResultMapper gateResultMapper;
    private final WebhookEventPublisher webhookEventPublisher;
    private final ObjectMapper objectMapper;

    @Override
    public GateResult checkGate(Long datasetId, Long runId) {
        return checkGate(JwtUtils.getCurrentUserId(), datasetId, runId);
    }

    @Override
    @Transactional
    public GateResult checkGate(Long userId, Long datasetId, Long runId) {
        AgentEvaluationDataset dataset = datasetMapper.selectById(datasetId);
        requireOwner(userId, dataset);

        AgentEvaluationRun run = runMapper.selectById(runId);
        if (run == null || !datasetId.equals(run.getDatasetId())) {
            throw new BusinessException("评测执行记录不存在或不属于该评测集: " + runId);
        }

        // 评测未完成（运行中/失败）时门禁直接不通过
        if (!"completed".equals(run.getStatus())) {
            Map<String, Object> blockedDetails = new LinkedHashMap<>();
            blockedDetails.put("run_status", run.getStatus());
            blockedDetails.put("error_detail", run.getErrorDetail() != null ? run.getErrorDetail() : "");
            blockedDetails.put("gate_record_id", 0L);
            GateResult blocked = GateResult.builder()
                    .datasetId(datasetId)
                    .runId(runId)
                    .runUuid(run.getRunUuid())
                    .passed(false)
                    .criteria(List.of())
                    .message("评测未完成（status=" + run.getStatus() + "），无法通过回归门禁")
                    .details(blockedDetails)
                    .checkedAt(LocalDateTime.now())
                    .build();
            persistGateResult(blocked, null, null);
            publishWebhookEvent(userId, blocked, run);
            return blocked;
        }

        Map<String, Object> summary = extractSummary(run);
        Double accuracy = run.getOverallScore();
        Double latencyP95 = extractDouble(summary, LATENCY_KEYS);
        Double tokenCost = extractDouble(summary, COST_KEYS);

        // 基线：同数据集最近一次 completed 且非本次的评测
        LambdaQueryWrapper<AgentEvaluationRun> baselineQuery = new LambdaQueryWrapper<>();
        baselineQuery
                .eq(AgentEvaluationRun::getDatasetId, datasetId)
                .eq(AgentEvaluationRun::getStatus, "completed")
                .ne(AgentEvaluationRun::getId, runId)
                .orderByDesc(AgentEvaluationRun::getCreatedAt)
                .orderByDesc(AgentEvaluationRun::getId)
                .last("LIMIT 1");
        AgentEvaluationRun baseline = runMapper.selectOne(baselineQuery);
        Double baselineTokenCost = null;
        if (baseline != null) {
            baselineTokenCost = extractDouble(extractSummary(baseline), COST_KEYS);
        }

        List<GateCriterion> criteria = new ArrayList<>(3);
        criteria.add(evaluateAccuracy(accuracy));
        criteria.add(evaluateLatency(latencyP95));
        criteria.add(evaluateTokenCost(tokenCost, baselineTokenCost));

        boolean passed = criteria.stream().noneMatch(c -> "FAILED".equals(c.getStatus()));
        String message = passed ? "回归门禁通过" : "回归门禁未通过，请检查失败的判定项";

        Map<String, Object> details = new LinkedHashMap<>();
        details.put("gate_record_id", 0L);
        details.put("baseline_run_uuid", baseline != null ? baseline.getRunUuid() : null);
        details.put("criteria_count", criteria.size());

        GateResult result = GateResult.builder()
                .datasetId(datasetId)
                .runId(runId)
                .runUuid(run.getRunUuid())
                .passed(passed)
                .accuracy(accuracy)
                .latencyP95(latencyP95)
                .tokenCost(tokenCost)
                .baselineRunUuid(baseline != null ? baseline.getRunUuid() : null)
                .baselineTokenCost(baselineTokenCost)
                .criteria(criteria)
                .message(message)
                .details(details)
                .checkedAt(LocalDateTime.now())
                .build();

        persistGateResult(result, baseline != null ? baseline.getRunUuid() : null, baselineTokenCost);
        publishWebhookEvent(userId, result, run);
        log.info(
                "评测门禁检查完成: dataset={} run={} passed={} score={} latency={} cost={}",
                datasetId,
                runId,
                passed,
                accuracy,
                latencyP95,
                tokenCost);
        return result;
    }

    @Override
    public List<EvaluationGateResult> gateHistory(Long userId, Long datasetId, int page, int pageSize) {
        requireOwner(userId, datasetMapper.selectById(datasetId));
        page = Math.max(1, page);
        pageSize = Math.max(1, Math.min(pageSize, 100));
        int offset = (page - 1) * pageSize;
        LambdaQueryWrapper<EvaluationGateResult> query = new LambdaQueryWrapper<>();
        query.eq(EvaluationGateResult::getDatasetId, datasetId)
                .orderByDesc(EvaluationGateResult::getCreatedAt)
                .orderByDesc(EvaluationGateResult::getId)
                .last("LIMIT " + offset + "," + pageSize);
        return gateResultMapper.selectList(query);
    }

    // ================================================================
    // 判定项
    // ================================================================

    /** 准确率：accuracy &gt; 0.80 */
    private GateCriterion evaluateAccuracy(Double accuracy) {
        GateCriterion.GateCriterionBuilder builder =
                GateCriterion.builder().name("accuracy").description("综合准确率").threshold("> " + ACCURACY_THRESHOLD);
        if (accuracy == null) {
            return builder.status("SKIPPED").actual("N/A").detail("评测未上报综合得分").build();
        }
        boolean passed = accuracy > ACCURACY_THRESHOLD;
        return builder.status(passed ? "PASSED" : "FAILED")
                .actual(String.format("%.4f", accuracy))
                .detail(passed ? "" : "低于门槛 " + ACCURACY_THRESHOLD)
                .build();
    }

    /** 延迟：latency_p95 &lt; 5000ms */
    private GateCriterion evaluateLatency(Double latencyP95) {
        GateCriterion.GateCriterionBuilder builder = GateCriterion.builder()
                .name("latency_p95")
                .description("P95 延迟（毫秒）")
                .threshold("< " + LATENCY_P95_MAX_MS);
        if (latencyP95 == null) {
            return builder.status("SKIPPED")
                    .actual("N/A")
                    .detail("评测未上报 P95 延迟")
                    .build();
        }
        boolean passed = latencyP95 < LATENCY_P95_MAX_MS;
        return builder.status(passed ? "PASSED" : "FAILED")
                .actual(String.format("%.1f", latencyP95))
                .detail(passed ? "" : "超出门槛 " + LATENCY_P95_MAX_MS + "ms")
                .build();
    }

    /** 成本：token_cost &lt; 基线 × 1.2（无基线时该项不构成回退，记 PASSED） */
    private GateCriterion evaluateTokenCost(Double tokenCost, Double baselineTokenCost) {
        GateCriterion.GateCriterionBuilder builder = GateCriterion.builder()
                .name("token_cost")
                .description("token 成本（美元）")
                .threshold("< 基线 × " + COST_BASELINE_RATIO);
        if (tokenCost == null) {
            return builder.status("SKIPPED")
                    .actual("N/A")
                    .detail("评测未上报 token 成本")
                    .build();
        }
        if (baselineTokenCost == null) {
            return builder.status("PASSED")
                    .actual(String.format("%.6f", tokenCost))
                    .detail("无基线可比，成本项不构成回退")
                    .build();
        }
        double limit = baselineTokenCost * COST_BASELINE_RATIO;
        boolean passed = tokenCost < limit;
        return builder.status(passed ? "PASSED" : "FAILED")
                .actual(String.format("%.6f", tokenCost))
                .threshold(String.format("< %.6f（基线 %.6f × %s）", limit, baselineTokenCost, COST_BASELINE_RATIO))
                .detail(
                        passed
                                ? ""
                                : "超出基线成本 " + String.format("%.6f", baselineTokenCost) + " 的 " + COST_BASELINE_RATIO
                                        + " 倍")
                .build();
    }

    // ================================================================
    // 持久化与事件
    // ================================================================

    private void persistGateResult(GateResult result, String baselineRunUuid, Double baselineTokenCost) {
        EvaluationGateResult entity = new EvaluationGateResult();
        entity.setDatasetId(result.getDatasetId());
        entity.setRunId(result.getRunId());
        entity.setRunUuid(result.getRunUuid());
        entity.setPassed(result.isPassed() ? 1 : 0);
        entity.setAccuracy(
                result.getAccuracy() != null
                        ? BigDecimal.valueOf(result.getAccuracy()).setScale(4, RoundingMode.HALF_UP)
                        : null);
        entity.setLatencyP95(result.getLatencyP95() != null ? (int) Math.round(result.getLatencyP95()) : null);
        entity.setTokenCost(
                result.getTokenCost() != null
                        ? BigDecimal.valueOf(result.getTokenCost()).setScale(6, RoundingMode.HALF_UP)
                        : null);
        entity.setBaselineRunUuid(baselineRunUuid);
        entity.setBaselineTokenCost(
                baselineTokenCost != null
                        ? BigDecimal.valueOf(baselineTokenCost).setScale(6, RoundingMode.HALF_UP)
                        : null);
        entity.setCriteriaJson(toJson(result.getCriteria()));
        entity.setDetails(toJson(result.getDetails()));
        gateResultMapper.insert(entity);
        result.getDetails().put("gate_record_id", entity.getId());
    }

    private void publishWebhookEvent(Long userId, GateResult result, AgentEvaluationRun run) {
        Long tenantId = TenantContext.getTenantId();
        if (tenantId == null) {
            log.debug("无租户上下文，跳过 evaluation.completed Webhook 发布");
            return;
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("datasetId", result.getDatasetId());
        payload.put("runId", result.getRunId());
        payload.put("runUuid", run.getRunUuid());
        payload.put("passed", result.isPassed());
        payload.put("accuracy", result.getAccuracy());
        payload.put("latency_p95", result.getLatencyP95());
        payload.put("token_cost", result.getTokenCost());
        payload.put("baseline_run_uuid", result.getBaselineRunUuid());
        payload.put("gate_record_id", result.getDetails().get("gate_record_id"));
        webhookEventPublisher.publish(WebhookEventTypes.EVALUATION_COMPLETED, tenantId, userId, payload);
    }

    // ================================================================
    // 内部辅助
    // ================================================================

    private void requireOwner(Long userId, AgentEvaluationDataset dataset) {
        if (dataset == null || userId == null || dataset.getUserId() == null || !userId.equals(dataset.getUserId())) {
            throw new BusinessException("unauthorized evaluation dataset");
        }
    }

    /** 从 caseResults 中提取 summary 映射 */
    @SuppressWarnings("unchecked")
    private Map<String, Object> extractSummary(AgentEvaluationRun run) {
        if (run.getCaseResults() == null) {
            return Map.of();
        }
        Object summary = run.getCaseResults().get("summary");
        if (summary instanceof Map) {
            return (Map<String, Object>) summary;
        }
        return Map.of();
    }

    /** 从 summary 中按候选键提取数值 */
    private Double extractDouble(Map<String, Object> summary, String... keys) {
        for (String key : keys) {
            Object value = summary.get(key);
            if (value instanceof Number number) {
                return number.doubleValue();
            }
            if (value instanceof String text) {
                try {
                    return Double.parseDouble(text);
                } catch (NumberFormatException ignored) {
                    // try next key
                }
            }
        }
        return null;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value != null ? value : Map.of());
        } catch (JsonProcessingException e) {
            log.warn("门禁结果序列化失败: {}", e.getMessage());
            return "{}";
        }
    }
}
