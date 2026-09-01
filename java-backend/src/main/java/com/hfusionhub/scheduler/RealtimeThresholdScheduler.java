package com.hfusionhub.scheduler;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.lock.SchedulerLock;
import com.hfusionhub.entity.AnalyticsRealtimeMetric;
import com.hfusionhub.mapper.AnalyticsRealtimeMetricMapper;
import java.time.LocalDateTime;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 实时指标阈值监控 — 每 60s 采样近 5 分钟窗口,经 Micrometer 暴露三个 gauge,
 * 由既有 Prometheus/Alertmanager 链路告警(见 deploy/monitoring/alert_rules.yml
 * 的 analytics 规则组),不引入新告警组件:
 *   analytics_request_rate_per_min   请求速率(次/分钟)
 *   analytics_cost_rate_per_min      成本速率(美元/分钟)
 *   analytics_avg_latency_ms         平均延迟(毫秒)
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RealtimeThresholdScheduler {

    private static final int WINDOW_MINUTES = 5;

    private final AnalyticsRealtimeMetricMapper realtimeMapper;

    private final AtomicReference<Double> requestRate = new AtomicReference<>(0d);
    private final AtomicReference<Double> costRate = new AtomicReference<>(0d);
    private final AtomicReference<Double> avgLatency = new AtomicReference<>(0d);

    @org.springframework.beans.factory.annotation.Autowired
    public void registerGauges(io.micrometer.core.instrument.MeterRegistry registry) {
        io.micrometer.core.instrument.Gauge.builder(
                        "analytics_request_rate_per_min", requestRate, ref -> ref.get())
                .description("LLM 调用速率(近5分钟, 次/分钟)")
                .register(registry);
        io.micrometer.core.instrument.Gauge.builder(
                        "analytics_cost_rate_per_min", costRate, ref -> ref.get())
                .description("LLM 成本速率(近5分钟, 美元/分钟)")
                .register(registry);
        io.micrometer.core.instrument.Gauge.builder(
                        "analytics_avg_latency_ms", avgLatency, ref -> ref.get())
                .description("LLM 平均延迟(近5分钟, 毫秒)")
                .register(registry);
    }

    @Scheduled(fixedDelay = 60_000)
    @SchedulerLock("analytics-threshold")
    public void sample() {
        // R17-10：采样线程无租户上下文；analytics_realtime_metrics 的 -1 行
        // 即平台全局口径（V82），显式 runAsSystem 固化该语义
        com.hfusionhub.tenant.TenantContext.runAsSystem(this::sampleInternal);
    }

    private void sampleInternal() {
        LocalDateTime since = LocalDateTime.now().minusMinutes(WINDOW_MINUTES);
        List<AnalyticsRealtimeMetric> rows = realtimeMapper.selectList(
                new LambdaQueryWrapper<AnalyticsRealtimeMetric>()
                        .gt(AnalyticsRealtimeMetric::getWindowStart, since));
        if (rows.isEmpty()) {
            requestRate.set(0d);
            costRate.set(0d);
            avgLatency.set(0d);
            return;
        }
        long requests = rows.stream()
                .mapToLong(r -> r.getRequestCount() == null ? 0 : r.getRequestCount()).sum();
        double cost = rows.stream()
                .mapToDouble(r -> r.getTotalCost() == null ? 0 : r.getTotalCost().doubleValue())
                .sum();
        double latency = rows.stream()
                .filter(r -> r.getRequestCount() != null && r.getRequestCount() > 0)
                .mapToLong(AnalyticsRealtimeMetric::getAvgLatencyMs)
                .average().orElse(0);

        requestRate.set(Math.round(requests / (double) WINDOW_MINUTES * 100) / 100.0);
        costRate.set(Math.round(cost / WINDOW_MINUTES * 10000) / 10000.0);
        avgLatency.set((double) Math.round(latency));
        log.debug("[analytics-threshold] rate/min={} cost/min={} avgLatencyMs={}",
                requestRate.get(), costRate.get(), avgLatency.get());
    }
}
