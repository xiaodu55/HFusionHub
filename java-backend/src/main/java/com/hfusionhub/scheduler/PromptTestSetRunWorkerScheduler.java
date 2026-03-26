package com.hfusionhub.scheduler;

import com.hfusionhub.entity.PromptTestSetRun;
import com.hfusionhub.service.PromptTestSetService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * 提示词测试用例集批量运行 Worker 调度器 — 定期认领并派发排队中的 Run，
 * 并对失联（running 超过阈值）的运行做恢复收敛。
 * 使用自管理 ScheduledExecutorService 替代 @Scheduled 以保证在 mvn spring-boot:run 下可靠运行。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class PromptTestSetRunWorkerScheduler implements ApplicationListener<ApplicationReadyEvent> {

    private final PromptTestSetService promptTestSetService;
    private final Executor runExecutor;
    private final boolean queueEnabled;
    private final long pollDelayMs;
    private final int batchSize;
    private final long recoveryDelayMs;
    private final long staleRunningMinutes;

    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2, r -> {
        Thread t = new Thread(r, "pts-run-worker-sched");
        t.setDaemon(true);
        return t;
    });

    public PromptTestSetRunWorkerScheduler(
            PromptTestSetService promptTestSetService,
            @Qualifier("promptTestSetRunExecutor") Executor runExecutor,
            @Value("${prompt-test-set.run.queue-enabled:false}") boolean queueEnabled,
            @Value("${prompt-test-set.run.poll-delay-ms:2000}") long pollDelayMs,
            @Value("${prompt-test-set.run.batch-size:5}") int batchSize,
            @Value("${prompt-test-set.run.recovery-delay-ms:30000}") long recoveryDelayMs,
            @Value("${prompt-test-set.run.stale-running-minutes:30}") long staleRunningMinutes) {
        this.promptTestSetService = promptTestSetService;
        this.runExecutor = runExecutor;
        this.queueEnabled = queueEnabled;
        this.pollDelayMs = pollDelayMs;
        this.batchSize = batchSize;
        this.recoveryDelayMs = recoveryDelayMs;
        this.staleRunningMinutes = staleRunningMinutes;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        if (!queueEnabled) {
            log.info("Prompt test set run queue disabled — async batch execution off");
            return;
        }
        log.info("Prompt test set run worker scheduler starting: poll={}ms recovery={}ms",
                pollDelayMs, recoveryDelayMs);

        scheduler.scheduleWithFixedDelay(this::pollAndDispatch, 1, pollDelayMs, TimeUnit.MILLISECONDS);
        scheduler.scheduleWithFixedDelay(this::recoverStaleRuns, 30, recoveryDelayMs, TimeUnit.MILLISECONDS);
    }

    private void pollAndDispatch() {
        try {
            List<PromptTestSetRun> queued = promptTestSetService.listQueuedRuns(batchSize);
            for (PromptTestSetRun run : queued) {
                if (promptTestSetService.claimRun(run.getId())) {
                    runExecutor.execute(() -> promptTestSetService.executeRun(run.getId()));
                }
            }
        } catch (Exception e) {
            log.error("Prompt test set run worker polling error", e);
        }
    }

    private void recoverStaleRuns() {
        try {
            promptTestSetService.markStaleRunsFailed(staleRunningMinutes);
        } catch (Exception e) {
            log.error("Prompt test set run recovery error", e);
        }
    }
}
