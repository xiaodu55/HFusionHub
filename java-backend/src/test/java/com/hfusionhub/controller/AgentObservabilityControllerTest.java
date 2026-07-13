package com.hfusionhub.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
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
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;
import org.mockito.Mockito;

/**
 * AgentObservabilityController 契约测试 — 覆盖全部 25 个端点。
 *
 * <p>纯 POJO 测试：mock 三个可观测性服务，mockStatic(JwtUtils) 提供当前用户，
 * 逐端点断言 R 信封与 service 委托参数。</p>
 */
class AgentObservabilityControllerTest {

    private static final Long USER_ID = 42L;

    private AgentMetricsService metricsService;
    private AgentAlertService alertService;
    private AgentEvaluationService evaluationService;
    private AgentObservabilityController controller;
    private MockedStatic<JwtUtils> jwtUtils;

    @BeforeEach
    void setUp() {
        metricsService = Mockito.mock(AgentMetricsService.class);
        alertService = Mockito.mock(AgentAlertService.class);
        evaluationService = Mockito.mock(AgentEvaluationService.class);
        controller = new AgentObservabilityController(metricsService, alertService, evaluationService);
        jwtUtils = Mockito.mockStatic(JwtUtils.class);
        jwtUtils.when(JwtUtils::getCurrentUserId).thenReturn(USER_ID);
    }

    @AfterEach
    void tearDown() {
        jwtUtils.close();
    }

    // ── 指标查询 ─────────────────────────────────────────────────────

    @Test
    void getTaskMetricsReturnsEnvelope() {
        when(metricsService.getTaskMetrics(USER_ID, 7L)).thenReturn(Mockito.mock(AgentMetricsDTO.class));

        R<AgentMetricsDTO> r = controller.getTaskMetrics(7L);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).isNotNull();
    }

    @Test
    void getTaskMetricsFailsWhenMissing() {
        when(metricsService.getTaskMetrics(USER_ID, 7L)).thenReturn(null);

        R<AgentMetricsDTO> r = controller.getTaskMetrics(7L);

        assertThat(r.getCode()).isNotEqualTo(200);
    }

    @Test
    void getRunMetricsReturnsEnvelope() {
        when(metricsService.getRunMetrics(USER_ID, 9L)).thenReturn(Mockito.mock(AgentMetricsDTO.class));

        R<AgentMetricsDTO> r = controller.getRunMetrics(9L);

        assertThat(r.getCode()).isEqualTo(200);
    }

    @Test
    void getRunMetricsFailsWhenMissing() {
        when(metricsService.getRunMetrics(USER_ID, 9L)).thenReturn(null);

        R<AgentMetricsDTO> r = controller.getRunMetrics(9L);

        assertThat(r.getCode()).isNotEqualTo(200);
    }

    @Test
    void listRunMetricsPassesFilters() {
        when(metricsService.listRunMetrics(eq(USER_ID), eq(1L), eq("running"), any(), any(), eq(2), eq(50)))
                .thenReturn(PageResult.of(2, 50, 0, List.of()));

        R<PageResult<AgentMetricsSummaryDTO>> r =
                controller.listRunMetrics(1L, "running", LocalDateTime.now(), LocalDateTime.now(), 2, 50);

        assertThat(r.getCode()).isEqualTo(200);
    }

    @Test
    void getAggregatedStatsPassesDays() {
        when(metricsService.getAggregatedStats(USER_ID, null, 7)).thenReturn(Mockito.mock(com.hfusionhub.dto.AgentAggregatedStatsDTO.class));

        R<com.hfusionhub.dto.AgentAggregatedStatsDTO> r = controller.getAggregatedStats(null, 7);

        assertThat(r.getCode()).isEqualTo(200);
        verify(metricsService).getAggregatedStats(eq(USER_ID), isNull(), eq(7));
    }

    @Test
    void getDashboardReturnsStats() {
        when(metricsService.getDashboardStats(USER_ID)).thenReturn(Map.of("runs", 3));

        R<Map<String, Object>> r = controller.getDashboard();

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).containsEntry("runs", 3);
    }

    // ── 告警规则 ─────────────────────────────────────────────────────

    @Test
    void listAlertRulesReturnsList() {
        when(alertService.listRules(USER_ID)).thenReturn(List.of(new AgentAlertRule()));

        R<List<AgentAlertRule>> r = controller.listAlertRules();

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).hasSize(1);
    }

    @Test
    void createAlertRuleDelegatesWithUserId() {
        AgentAlertRule rule = new AgentAlertRule();
        when(alertService.createRule(USER_ID, rule)).thenReturn(rule);

        R<AgentAlertRule> r = controller.createAlertRule(rule);

        assertThat(r.getCode()).isEqualTo(200);
        verify(alertService).createRule(USER_ID, rule);
    }

    @Test
    void updateAlertRuleBindsPathIdIntoBody() {
        AgentAlertRule rule = new AgentAlertRule();
        when(alertService.updateRule(USER_ID, rule)).thenReturn(rule);

        R<AgentAlertRule> r = controller.updateAlertRule(5L, rule);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(rule.getId()).isEqualTo(5L);
        verify(alertService).updateRule(USER_ID, rule);
    }

    @Test
    void deleteAlertRuleDelegates() {
        R<String> r = controller.deleteAlertRule(5L);

        assertThat(r.getCode()).isEqualTo(200);
        verify(alertService).deleteRule(USER_ID, 5L);
    }

    // ── 告警事件 ─────────────────────────────────────────────────────

    @Test
    void listAlertEventsPaginates() {
        when(alertService.listAlertEvents(USER_ID, 1, 20))
                .thenReturn(PageResult.of(1, 20, 0, List.of()));

        R<PageResult<AgentAlertEvent>> r = controller.listAlertEvents(1, 20);

        assertThat(r.getCode()).isEqualTo(200);
    }

    @Test
    void listUnresolvedAlertsReturnsList() {
        when(alertService.listUnresolvedAlerts(USER_ID)).thenReturn(List.of(new AgentAlertEvent()));

        R<List<AgentAlertEvent>> r = controller.listUnresolvedAlerts();

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).hasSize(1);
    }

    @Test
    void resolveAlertDelegates() {
        R<String> r = controller.resolveAlert(11L);

        assertThat(r.getCode()).isEqualTo(200);
        verify(alertService).resolveAlert(USER_ID, 11L);
    }

    @Test
    void checkAlertsReturnsTriggeredEvents() {
        when(alertService.checkAlerts(USER_ID)).thenReturn(List.of(new AgentAlertEvent()));

        R<List<AgentAlertEvent>> r = controller.checkAlerts();

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).hasSize(1);
    }

    // ── 评测集管理 ───────────────────────────────────────────────────

    @Test
    void createDatasetBindsCurrentUserId() {
        AgentEvaluationDataset dataset = new AgentEvaluationDataset();
        when(evaluationService.createDataset(dataset)).thenReturn(dataset);

        R<AgentEvaluationDataset> r = controller.createDataset(dataset);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(dataset.getUserId()).isEqualTo(USER_ID);
        verify(evaluationService).createDataset(dataset);
    }

    @Test
    void getDatasetReturnsEnvelope() {
        when(evaluationService.getDataset(USER_ID, 3L)).thenReturn(new AgentEvaluationDataset());

        R<AgentEvaluationDataset> r = controller.getDataset(3L);

        assertThat(r.getCode()).isEqualTo(200);
    }

    @Test
    void listDatasetsPaginates() {
        when(evaluationService.listDatasets(USER_ID, null, 1, 20))
                .thenReturn(List.of(new AgentEvaluationDataset()));

        R<List<AgentEvaluationDataset>> r = controller.listDatasets(null, 1, 20);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).hasSize(1);
    }

    @Test
    void deleteDatasetDelegates() {
        R<String> r = controller.deleteDataset(3L);

        assertThat(r.getCode()).isEqualTo(200);
        verify(evaluationService).deleteDataset(USER_ID, 3L);
    }

    @Test
    void addCaseBindsDatasetId() {
        AgentEvaluationCase evalCase = new AgentEvaluationCase();
        when(evaluationService.addCase(USER_ID, evalCase)).thenReturn(evalCase);

        R<AgentEvaluationCase> r = controller.addCase(3L, evalCase);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(evalCase.getDatasetId()).isEqualTo(3L);
        verify(evaluationService).addCase(USER_ID, evalCase);
    }

    @Test
    void getCasesReturnsList() {
        when(evaluationService.getCases(USER_ID, 3L)).thenReturn(List.of(new AgentEvaluationCase()));

        R<List<AgentEvaluationCase>> r = controller.getCases(3L);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).hasSize(1);
    }

    @Test
    void deleteCaseDelegates() {
        R<String> r = controller.deleteCase(8L);

        assertThat(r.getCode()).isEqualTo(200);
        verify(evaluationService).deleteCase(USER_ID, 8L);
    }

    // ── 评测执行 ─────────────────────────────────────────────────────

    @Test
    void runEvaluationPassesUserAsSecondArg() {
        when(evaluationService.runEvaluation(3L, USER_ID)).thenReturn(new AgentEvaluationRun());

        R<AgentEvaluationRun> r = controller.runEvaluation(3L);

        assertThat(r.getCode()).isEqualTo(200);
        verify(evaluationService).runEvaluation(3L, USER_ID);
    }

    @Test
    void listEvaluationRunsPaginates() {
        when(evaluationService.listEvaluationRuns(USER_ID, 3L, 1, 20))
                .thenReturn(List.of(new AgentEvaluationRun()));

        R<List<AgentEvaluationRun>> r = controller.listEvaluationRuns(3L, 1, 20);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).hasSize(1);
    }

    @Test
    void getEvaluationRunReturnsEnvelope() {
        when(evaluationService.getEvaluationRun(USER_ID, 6L)).thenReturn(new AgentEvaluationRun());

        R<AgentEvaluationRun> r = controller.getEvaluationRun(6L);

        assertThat(r.getCode()).isEqualTo(200);
    }

    // ── 回归门禁 ─────────────────────────────────────────────────────

    @Test
    void checkRegressionGateReturnsResult() {
        when(evaluationService.checkRegressionGate(USER_ID, 3L)).thenReturn(Map.of("passed", true));

        R<Map<String, Object>> r = controller.checkRegressionGate(3L);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).containsEntry("passed", true);
    }

    @Test
    void getGateThresholdsReturnsDefaults() {
        when(evaluationService.getDefaultGateThresholds()).thenReturn(Map.of("hitAt5", 0.85));

        R<Map<String, Double>> r = controller.getGateThresholds();

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).containsEntry("hitAt5", 0.85);
    }
}
