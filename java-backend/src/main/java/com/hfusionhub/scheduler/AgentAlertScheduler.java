package com.hfusionhub.scheduler;

import com.hfusionhub.service.AgentAlertService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Agent 告警定时检查 — 每 5 分钟对所有活跃用户执行告警规则检查。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AgentAlertScheduler {

    private final AgentAlertService alertService;

    /**
     * 每 5 分钟执行一次告警检查。
     */
    @Scheduled(fixedRate = 300_000)
    public void runAlertChecks() {
        log.debug("Starting scheduled agent alert checks...");
        try {
            var events = alertService.checkAllActiveAlerts();
            if (!events.isEmpty()) {
                log.warn("Alert check triggered {} new alert events", events.size());
                for (var event : events) {
                    log.warn("  └─ [{}] {}: {}", event.getSeverity(), event.getRuleName(), event.getMessage());
                }
            }
        } catch (Exception e) {
            log.error("Scheduled alert check failed", e);
        }
    }
}
