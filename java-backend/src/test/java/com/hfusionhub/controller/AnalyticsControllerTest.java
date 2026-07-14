package com.hfusionhub.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.AdsCostDaily;
import com.hfusionhub.entity.AnalyticsRealtimeMetric;
import com.hfusionhub.service.AnalyticsService;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * AnalyticsController 契约测试 — 运营大屏接口(分析扩展包)。
 */
@ExtendWith(MockitoExtension.class)
class AnalyticsControllerTest {

    @Mock
    private AnalyticsService analyticsService;

    private AnalyticsController controller;

    @BeforeEach
    void setUp() {
        controller = new AnalyticsController(analyticsService);
    }

    @Test
    void overviewReturnsEnvelope() {
        when(analyticsService.overview(7)).thenReturn(Map.of(
                "totalCalls", 120L, "totalCostUsd", 3.14));

        R<Map<String, Object>> r = controller.overview(7);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).containsEntry("totalCalls", 120L);
        verify(analyticsService).overview(7);
    }

    @Test
    void costDailyMapsEntityRows() {
        AdsCostDaily row = new AdsCostDaily();
        row.setTenantId(1L);
        row.setStatDate(LocalDate.of(2026, 8, 30));
        row.setCallCount(10L);
        row.setTotalTokens(1000L);
        row.setCostUsd(new BigDecimal("0.5"));
        row.setEstMonthCost(new BigDecimal("15.00"));
        when(analyticsService.costDaily(7, null)).thenReturn(List.of(row));

        R<List<Map<String, Object>>> r = controller.costDaily(7, null);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).hasSize(1);
        assertThat(r.getData().get(0)).containsEntry("callCount", 10L);
        assertThat(r.getData().get(0)).containsEntry("estMonthCost",
                new BigDecimal("15.00"));
    }

    @Test
    void realtimeMapsWindowRows() {
        AnalyticsRealtimeMetric metric = new AnalyticsRealtimeMetric();
        metric.setTenantId(1L);
        metric.setModel("deepseek-v4-flash");
        metric.setWindowStart(LocalDateTime.of(2026, 8, 30, 10, 0));
        metric.setWindowEnd(LocalDateTime.of(2026, 8, 30, 10, 1));
        metric.setRequestCount(12L);
        metric.setTotalTokens(8000L);
        metric.setTotalCost(new BigDecimal("0.02"));
        metric.setAvgLatencyMs(1500L);
        metric.setMaxLatencyMs(4000L);
        when(analyticsService.realtime(60, 1L)).thenReturn(List.of(metric));

        R<List<Map<String, Object>>> r = controller.realtime(60, 1L);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).hasSize(1);
        assertThat(r.getData().get(0)).containsEntry("model", "deepseek-v4-flash");
        verify(analyticsService).realtime(60, 1L);
    }

    @Test
    void emptyTablesReturnEmptyListNotError() {
        // 分析扩展包未部署时 ADS 表为空 —— 空集而非报错(主产品零依赖)
        when(analyticsService.costDaily(7, 1L)).thenReturn(List.of());

        R<List<Map<String, Object>>> r = controller.costDaily(7, 1L);

        assertThat(r.getCode()).isEqualTo(200);
        assertThat(r.getData()).isEmpty();
    }
}
