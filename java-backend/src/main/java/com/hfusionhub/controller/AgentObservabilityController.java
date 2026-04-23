package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.AgentAggregatedStatsDTO;
import com.hfusionhub.dto.AgentMetricsDTO;
import com.hfusionhub.dto.AgentMetricsSummaryDTO;
import com.hfusionhub.entity.AgentAlertEvent;
import com.hfusionhub.entity.AgentAlertRule;
import com.hfusionhub.entity.AgentEvaluationCase;
import com.hfusionhub.entity.AgentEvaluationDataset;
import com.hfusionhub.entity.AgentEvaluationRun;
import com.hfusionhub.service.AgentAlertService;
import com.hfusionhub.service.AgentEvaluationService;
import com.hfusionhub.service.AgentMetricsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.*;

/**
 * Agent 可观测性统一控制器 — 整合指标、告警 API
 *
 * 所有读操作均校验 JWT 用户身份。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Tag(name = "Agent可观测性", description = "Agent运行指标、聚合统计与告警管理")
@RestController
@RequestMapping("/agent-observability")
@RequiredArgsConstructor
public class AgentObservabilityController {

    private final AgentMetricsService metricsService;
    private final AgentAlertService alertService;
    private final AgentEvaluationService evaluationService;

    // ================================================================
    // 指标查询
    // ================================================================

    @Operation(summary = "获取单任务指标")
    @GetMapping("/metrics/tasks/{taskId}")
    public R<AgentMetricsDTO> getTaskMetrics(@PathVariable Long taskId) {
        AgentMetricsDTO metrics = metricsService.getTaskMetrics(JwtUtils.getCurrentUserId(), taskId);
        if (metrics == null) return R.fail("任务不存在");
        return R.ok(metrics);
    }

    @Operation(summary = "获取单Run指标")
    @GetMapping("/metrics/runs/{runId}")
    public R<AgentMetricsDTO> getRunMetrics(@PathVariable Long runId) {
        AgentMetricsDTO metrics = metricsService.getRunMetrics(JwtUtils.getCurrentUserId(), runId);
        if (metrics == null) return R.fail("Run记录不存在");
        return R.ok(metrics);
    }

    @Operation(summary = "查询Run指标列表(分页+筛选)")
    @GetMapping("/metrics/runs")
    public R<PageResult<AgentMetricsSummaryDTO>> listRunMetrics(
            @RequestParam(required = false) Long kbId,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime start,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime end,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(metricsService.listRunMetrics(userId, kbId, status, start, end, page, pageSize));
    }

    @Operation(summary = "聚合统计(按用户/知识库/时间窗口)")
    @GetMapping("/metrics/stats")
    public R<AgentAggregatedStatsDTO> getAggregatedStats(
            @RequestParam(required = false) Long kbId, @RequestParam(defaultValue = "7") int days) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(metricsService.getAggregatedStats(userId, kbId, days));
    }

    @Operation(summary = "Dashboard概览")
    @GetMapping("/dashboard")
    public R<Map<String, Object>> getDashboard() {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(metricsService.getDashboardStats(userId));
    }

    // ================================================================
    // 告警规则管理
    // ================================================================

    @Operation(summary = "获取告警规则列表")
    @GetMapping("/alerts/rules")
    public R<List<AgentAlertRule>> listAlertRules() {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(alertService.listRules(userId));
    }

    @Operation(summary = "创建告警规则")
    @PostMapping("/alerts/rules")
    public R<AgentAlertRule> createAlertRule(@RequestBody AgentAlertRule rule) {
        return R.ok(alertService.createRule(JwtUtils.getCurrentUserId(), rule));
    }

    @Operation(summary = "更新告警规则")
    @PutMapping("/alerts/rules/{ruleId}")
    public R<AgentAlertRule> updateAlertRule(@PathVariable Long ruleId, @RequestBody AgentAlertRule rule) {
        rule.setId(ruleId);
        return R.ok(alertService.updateRule(JwtUtils.getCurrentUserId(), rule));
    }

    @Operation(summary = "删除告警规则")
    @DeleteMapping("/alerts/rules/{ruleId}")
    public R<String> deleteAlertRule(@PathVariable Long ruleId) {
        alertService.deleteRule(JwtUtils.getCurrentUserId(), ruleId);
        return R.ok("已删除");
    }

    // ================================================================
    // 告警事件管理
    // ================================================================

    @Operation(summary = "查询告警事件列表")
    @GetMapping("/alerts/events")
    public R<PageResult<AgentAlertEvent>> listAlertEvents(
            @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(alertService.listAlertEvents(userId, page, pageSize));
    }

    @Operation(summary = "获取未解除的告警")
    @GetMapping("/alerts/events/unresolved")
    public R<List<AgentAlertEvent>> listUnresolvedAlerts() {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(alertService.listUnresolvedAlerts(userId));
    }

    @Operation(summary = "解除告警")
    @PostMapping("/alerts/events/{alertId}/resolve")
    public R<String> resolveAlert(@PathVariable Long alertId) {
        alertService.resolveAlert(JwtUtils.getCurrentUserId(), alertId);
        return R.ok("已解除");
    }

    @Operation(summary = "手动触发告警检查")
    @PostMapping("/alerts/check")
    public R<List<AgentAlertEvent>> checkAlerts() {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(alertService.checkAlerts(userId));
    }

    // ================================================================
    // 评测集管理
    // ================================================================

    @Operation(summary = "创建评测集")
    @PostMapping("/evaluation/datasets")
    public R<AgentEvaluationDataset> createDataset(@RequestBody AgentEvaluationDataset dataset) {
        dataset.setUserId(JwtUtils.getCurrentUserId());
        return R.ok(evaluationService.createDataset(dataset));
    }

    @Operation(summary = "获取评测集详情")
    @GetMapping("/evaluation/datasets/{datasetId}")
    public R<AgentEvaluationDataset> getDataset(@PathVariable Long datasetId) {
        return R.ok(evaluationService.getDataset(JwtUtils.getCurrentUserId(), datasetId));
    }

    @Operation(summary = "评测集列表")
    @GetMapping("/evaluation/datasets")
    public R<List<AgentEvaluationDataset>> listDatasets(
            @RequestParam(required = false) Long kbId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(evaluationService.listDatasets(userId, kbId, page, pageSize));
    }

    @Operation(summary = "删除评测集")
    @DeleteMapping("/evaluation/datasets/{datasetId}")
    public R<String> deleteDataset(@PathVariable Long datasetId) {
        evaluationService.deleteDataset(JwtUtils.getCurrentUserId(), datasetId);
        return R.ok("已删除");
    }

    // ── 用例管理 ──

    @Operation(summary = "添加评测用例")
    @PostMapping("/evaluation/datasets/{datasetId}/cases")
    public R<AgentEvaluationCase> addCase(@PathVariable Long datasetId, @RequestBody AgentEvaluationCase evalCase) {
        evalCase.setDatasetId(datasetId);
        return R.ok(evaluationService.addCase(JwtUtils.getCurrentUserId(), evalCase));
    }

    @Operation(summary = "获取评测用例列表")
    @GetMapping("/evaluation/datasets/{datasetId}/cases")
    public R<List<AgentEvaluationCase>> getCases(@PathVariable Long datasetId) {
        return R.ok(evaluationService.getCases(JwtUtils.getCurrentUserId(), datasetId));
    }

    @Operation(summary = "删除评测用例")
    @DeleteMapping("/evaluation/cases/{caseId}")
    public R<String> deleteCase(@PathVariable Long caseId) {
        evaluationService.deleteCase(JwtUtils.getCurrentUserId(), caseId);
        return R.ok("已删除");
    }

    // ── 评测执行 ──

    @Operation(summary = "执行离线评测")
    @PostMapping("/evaluation/datasets/{datasetId}/run")
    public R<AgentEvaluationRun> runEvaluation(@PathVariable Long datasetId) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(evaluationService.runEvaluation(datasetId, userId));
    }

    @Operation(summary = "评测执行历史")
    @GetMapping("/evaluation/datasets/{datasetId}/runs")
    public R<List<AgentEvaluationRun>> listEvaluationRuns(
            @PathVariable Long datasetId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return R.ok(evaluationService.listEvaluationRuns(JwtUtils.getCurrentUserId(), datasetId, page, pageSize));
    }

    @Operation(summary = "获取单次评测执行详情")
    @GetMapping("/evaluation/runs/{runId}")
    public R<AgentEvaluationRun> getEvaluationRun(@PathVariable Long runId) {
        return R.ok(evaluationService.getEvaluationRun(JwtUtils.getCurrentUserId(), runId));
    }

    // ── 回归门禁 ──

    @Operation(summary = "检查回归门禁")
    @PostMapping("/evaluation/datasets/{datasetId}/gate-check")
    public R<Map<String, Object>> checkRegressionGate(@PathVariable Long datasetId) {
        return R.ok(evaluationService.checkRegressionGate(JwtUtils.getCurrentUserId(), datasetId));
    }

    @Operation(summary = "获取默认门禁阈值")
    @GetMapping("/evaluation/gate-thresholds")
    public R<Map<String, Double>> getGateThresholds() {
        return R.ok(evaluationService.getDefaultGateThresholds());
    }
}
