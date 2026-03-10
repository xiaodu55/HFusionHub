package com.hfusionhub.scheduler;

import com.hfusionhub.service.AgentTaskService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 审批超时定时任务 — 每分钟检查一次过期审批并自动拒绝
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ApprovalExpiryScheduler {

    private final AgentTaskService agentTaskService;

    @Scheduled(fixedDelay = 60_000)
    public void expireApprovals() {
        try {
            int count = agentTaskService.expireApprovals();
            if (count > 0) {
                log.info("Expired {} pending approvals", count);
            }
        } catch (Exception e) {
            log.error("Failed to expire approvals", e);
        }
    }
}
