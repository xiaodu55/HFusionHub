package com.hfusionhub.scheduler;

import com.hfusionhub.service.AgentStatusEventService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Agent 状态事件清理调度器 — 定期清理过期状态事件
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AgentStatusEventCleanupScheduler {

    private final AgentStatusEventService statusEventService;

    @Scheduled(cron = "0 30 3 * * ?")
    public void cleanupEvents() {
        try {
            int deleted = statusEventService.cleanupEvents();
            log.debug("Cleaned up {} expired agent status events", deleted);
        } catch (Exception e) {
            log.error("Agent status event cleanup error", e);
        }
    }
}
