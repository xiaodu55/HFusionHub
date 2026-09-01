package com.hfusionhub.scheduler;

import com.hfusionhub.service.AgentTaskQueueService;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * Prometheus gauge 暴露 agent 任务队列深度（pending Run 数）。
 *
 * <p>供 deploy/monitoring/alert_rules.yml 的 AgentQueueBacklogHigh 告警消费。
 * 依赖 Spring Boot Actuator 自动装配的 {@link MeterRegistry}（micrometer-registry-prometheus），
 * 与 java-backend 的 {@code /api/actuator/prometheus} 端点共用同一注册表。
 * gauge 的采样函数是惰性的——仅在 Prometheus scrape 时才查询数据库，不影响启动。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class AgentQueueGauge {

    private final AgentTaskQueueService queueService;

    public AgentQueueGauge(AgentTaskQueueService queueService, MeterRegistry meterRegistry) {
        this.queueService = queueService;
        Gauge.builder("agent_queue_depth", this::safeCount)
                .description("Number of pending agent runs waiting in the queue")
                .register(meterRegistry);
    }

    private double safeCount() {
        try {
            // R17-10：gauge 采样线程无租户上下文，租户拦截器 fail-closed 只读
            // -1 行导致队列深度恒 0（AgentQueueBacklogHigh 告警失效）——
            // 队列深度是平台级口径，显式 runAsSystem。
            return com.hfusionhub.tenant.TenantContext.runAsSystem(() -> queueService.countQueuedRuns());
        } catch (Exception e) {
            // Scrape must never fail the whole /actuator/prometheus endpoint; a
            // DB blip reports 0 and logs instead of dropping every metric.
            log.warn("agent_queue_depth gauge query failed", e);
            return 0.0;
        }
    }
}
