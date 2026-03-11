package com.hfusionhub.scheduler;

import com.hfusionhub.service.AgentTaskQueueService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Agent 任务队列轮询调度器 — 定期认领并派发待执行的 Run。
 * 使用自管理 ScheduledExecutorService 替代 @Scheduled 以保证在 mvn spring-boot:run 环境下可靠运行。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class AgentTaskWorkerScheduler implements ApplicationListener<ApplicationReadyEvent> {

    private final AgentTaskQueueService queueService;
    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2, r -> {
        Thread t = new Thread(r, "agent-worker-sched");
        t.setDaemon(true);
        return t;
    });

    public AgentTaskWorkerScheduler(AgentTaskQueueService queueService,
                                    @Qualifier("agentWorkerExecutor") java.util.concurrent.Executor agentWorkerExecutor) {
        this.queueService = queueService;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        log.info("Agent worker scheduler starting: poll=5s heartbeat=15s");

        // Poll every 5s — uses agent worker executor internally for execution
        scheduler.scheduleWithFixedDelay(() -> {
            try {
                int dispatched = queueService.pollAndDispatch();
                if (dispatched > 0) {
                    log.info("Worker dispatched {} agent runs", dispatched);
                }
            } catch (Exception e) {
                log.error("Agent task worker polling error", e);
            }
        }, 5, 5, TimeUnit.SECONDS);

        // Heartbeat every 15s
        scheduler.scheduleWithFixedDelay(() -> {
            try {
                queueService.heartbeatInFlightRuns();
            } catch (Exception e) {
                log.error("Agent task heartbeat error", e);
            }
        }, 15, 15, TimeUnit.SECONDS);
    }
}
