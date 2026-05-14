package com.hfusionhub.scheduler;

import com.hfusionhub.common.lock.SchedulerLock;
import com.hfusionhub.service.AgentTaskService;
import com.hfusionhub.tenant.TenantContext;
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

    @SchedulerLock("approval-expiry")
    @Scheduled(fixedDelay = 60_000)
    public void expireApprovals() {
        try {
            int count = TenantContext.runAsSystem(agentTaskService::expireApprovals);
            if (count > 0) {
                log.info("Expired {} pending approvals", count);
            }
        } catch (Exception e) {
            log.error("Failed to expire approvals", e);
        }
    }
}
