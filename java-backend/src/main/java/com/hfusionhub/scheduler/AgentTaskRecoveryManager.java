package com.hfusionhub.scheduler;

import com.hfusionhub.service.AgentTaskQueueService;
import com.hfusionhub.tenant.TenantContext;
import java.util.concurrent.CompletableFuture;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

/**
 * Agent 任务启动恢复管理器 — 应用就绪后立即执行一次全面恢复扫描。
 * 使用 ApplicationReadyEvent（非 @PostConstruct）确保 DataSource/Redis 完全初始化。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AgentTaskRecoveryManager implements ApplicationListener<ApplicationReadyEvent> {

    private final AgentTaskQueueService queueService;

    @Value("${agent.recovery.startup-recovery:true}")
    private boolean startupRecovery;

    @org.springframework.beans.factory.annotation.Qualifier("agentWorkerExecutor")
    private final ThreadPoolTaskExecutor agentWorkerExecutor;

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        if (!startupRecovery) {
            log.info("Startup recovery disabled via config — skipping");
            return;
        }
        log.info("Starting agent task recovery on application ready...");
        // Run async on worker executor to avoid blocking startup
        CompletableFuture.runAsync(
                () -> {
                    try {
                        int recovered = TenantContext.runAsSystem(queueService::recoverAll);
                        log.info("Startup recovery completed: {} runs processed", recovered);
                    } catch (Exception e) {
                        log.error("Startup recovery error", e);
                    }
                },
                agentWorkerExecutor);
    }
}
