package com.hfusionhub.scheduler;

import com.hfusionhub.service.AgentTaskQueueService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Agent 任务恢复调度器 — 定期扫描孤儿 Run、超时看门狗、Task 收敛、死信到期处理。
 * 使用自管理 ScheduledExecutorService 以保证可靠运行。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class AgentTaskRecoveryScheduler implements ApplicationListener<ApplicationReadyEvent> {

    private final AgentTaskQueueService queueService;
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "agent-recovery-sched");
        t.setDaemon(true);
        return t;
    });

    public AgentTaskRecoveryScheduler(AgentTaskQueueService queueService) {
        this.queueService = queueService;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        log.info("Agent recovery scheduler starting: sweep every 30s");
        scheduler.scheduleWithFixedDelay(() -> {
            try {
                int recovered = queueService.recoverAll();
                if (recovered > 0) {
                    log.info("Recovery sweep: {} runs processed", recovered);
                }
            } catch (Exception e) {
                log.error("Agent task recovery sweep error", e);
            }
        }, 30, 30, TimeUnit.SECONDS);
    }
}
