package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.service.AnalyticsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 运营分析大屏接口(HFusionData Analytics)。
 *
 * <p>数据源: Spark ADS 的 MySQL 镜像 + Flink 实时指标,业务侧零 Hadoop 依赖。
 * 租户隔离在 Service 层强制:普通用户仅本租户;平台管理员可传 tenantId
 * (null=全部,-1=平台全局)。分析扩展包未启用时这些表为空,接口返回空集
 * 而非报错 —— 主产品零依赖。</p>
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/analytics")
@RequiredArgsConstructor
@Tag(name = "运营分析", description = "AI 平台运营数仓大屏(分析扩展包)")
public class AnalyticsController {

    private final AnalyticsService analyticsService;

    @GetMapping("/overview")
    @Operation(summary = "分析概览(近 N 天累计 + 近 5 分钟实时速率)")
    public R<Map<String, Object>> overview(@RequestParam(defaultValue = "7") int days) {
        return R.ok(analyticsService.overview(days));
    }

    @GetMapping("/cost-daily")
    @Operation(summary = "每日成本趋势")
    public R<List<Map<String, Object>>> costDaily(
            @RequestParam(defaultValue = "7") int days,
            @RequestParam(required = false) Long tenantId) {
        return R.ok(analyticsService.costDaily(days, tenantId).stream()
                .map(r -> {
                    Map<String, Object> row = new HashMap<>();
                    row.put("tenantId", r.getTenantId());
                    row.put("statDate", String.valueOf(r.getStatDate()));
                    row.put("callCount", r.getCallCount());
                    row.put("totalTokens", r.getTotalTokens());
                    row.put("costUsd", r.getCostUsd());
                    row.put("estMonthCost", r.getEstMonthCost());
                    return row;
                })
                .toList());
    }

    @GetMapping("/model-share")
    @Operation(summary = "模型成本占比(默认 T-1)")
    public R<List<Map<String, Object>>> modelShare(
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date,
            @RequestParam(required = false) Long tenantId) {
        return R.ok(analyticsService.modelShare(date, tenantId).stream()
                .map(r -> {
                    Map<String, Object> row = new HashMap<>();
                    row.put("tenantId", r.getTenantId());
                    row.put("model", r.getModel());
                    row.put("statDate", String.valueOf(r.getStatDate()));
                    row.put("callCount", r.getCallCount());
                    row.put("costUsd", r.getCostUsd());
                    row.put("costShare", r.getCostShare());
                    return row;
                })
                .toList());
    }

    @GetMapping("/tool-success")
    @Operation(summary = "Agent 步骤成功率")
    public R<List<Map<String, Object>>> toolSuccess(
            @RequestParam(defaultValue = "7") int days,
            @RequestParam(required = false) Long tenantId) {
        return R.ok(analyticsService.toolSuccess(days, tenantId).stream()
                .map(r -> {
                    Map<String, Object> row = new HashMap<>();
                    row.put("tenantId", r.getTenantId());
                    row.put("stepType", r.getStepType());
                    row.put("statDate", String.valueOf(r.getStatDate()));
                    row.put("stepCount", r.getStepCount());
                    row.put("errorCount", r.getErrorCount());
                    row.put("successRate", r.getSuccessRate());
                    return row;
                })
                .toList());
    }

    @GetMapping("/eval-quality")
    @Operation(summary = "检索/评测质量趋势")
    public R<List<Map<String, Object>>> evalQuality(
            @RequestParam(defaultValue = "30") int days,
            @RequestParam(required = false) Long tenantId) {
        return R.ok(analyticsService.evalQuality(days, tenantId).stream()
                .map(r -> {
                    Map<String, Object> row = new HashMap<>();
                    row.put("tenantId", r.getTenantId());
                    row.put("statDate", String.valueOf(r.getStatDate()));
                    row.put("evalCount", r.getEvalCount());
                    row.put("avgHitRatio", r.getAvgHitRatio());
                    row.put("avgLatencyMs", r.getAvgLatencyMs());
                    row.put("failureRate", r.getFailureRate());
                    return row;
                })
                .toList());
    }

    @GetMapping("/realtime")
    @Operation(summary = "实时指标(近 N 分钟,1min 窗口)")
    public R<List<Map<String, Object>>> realtime(
            @RequestParam(defaultValue = "60") int minutes,
            @RequestParam(required = false) Long tenantId) {
        return R.ok(analyticsService.realtime(minutes, tenantId).stream()
                .map(r -> {
                    Map<String, Object> row = new HashMap<>();
                    row.put("tenantId", r.getTenantId());
                    row.put("model", r.getModel());
                    row.put("windowStart", String.valueOf(r.getWindowStart()));
                    row.put("windowEnd", String.valueOf(r.getWindowEnd()));
                    row.put("requestCount", r.getRequestCount());
                    row.put("totalTokens", r.getTotalTokens());
                    row.put("totalCost", r.getTotalCost());
                    row.put("avgLatencyMs", r.getAvgLatencyMs());
                    row.put("maxLatencyMs", r.getMaxLatencyMs());
                    return row;
                })
                .toList());
    }
}
