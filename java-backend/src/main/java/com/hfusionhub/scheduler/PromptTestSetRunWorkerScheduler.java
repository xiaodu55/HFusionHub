package com.hfusionhub.scheduler;

import com.hfusionhub.entity.PromptTestSetRun;
import com.hfusionhub.service.PromptTestSetService;
import com.hfusionhub.tenant.TenantContext;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.SmartLifecycle;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.locks.ReentrantLock;

/**
 * 提示词测试用例集批量运行 Worker 调度器 — 定期认领并派发排队中的 Run，
 * 并对失联（running 超过阈值）的运行做恢复收敛。
 * 使用自管理 ScheduledExecutorService 替代 @Scheduled 以保证在 mvn spring-boot:run 下可靠运行。
 *
 * <p>优雅停机（{@link SmartLifecycle}）：Spring 上下文关闭时先停止轮询（不再认领/派发新任务），
 * 再在限定时间内等待已提交到运行线程池的批量任务结束，从而避免重启时遗留「已认领但无人执行」
 * 的无主任务；超时未结束的任务由下次启动的 stale-run 恢复扫描兜底。
 *
 * <p>并发控制：{@link #dispatchLock} 这一把锁同时保护「停机标志 + 认领 + 提交 + 登记 Future」，
 * 因此一次派发周期要么在停机前整体完成（其提交的任务全部已被登记进 {@link #inFlight}），
 * 要么在停机后读到停机标志立即返回、不再认领——不会出现「停机后才开始认领/派发」的竞争窗口。
 * 每个任务的 {@code finally} 会从 {@link #inFlight} 移除自身 Future，避免长期运行累积历史任务。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class PromptTestSetRunWorkerScheduler implements ApplicationListener<ApplicationReadyEvent>, SmartLifecycle {

    /** 与运行线程池（ExecutorLifecycle, phase=Integer.MAX_VALUE）同为最高优先级，尽力先停止轮询。 */
    private static final int SHUTDOWN_PHASE = Integer.MAX_VALUE;

    private final PromptTestSetService promptTestSetService;
    private final AsyncTaskExecutor runExecutor;
    private final boolean queueEnabled;
    private final long pollDelayMs;
    private final int batchSize;
    private final long recoveryDelayMs;
    private final long staleRunningMinutes;
    private final long shutdownTimeoutMs;

    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2, r -> {
        Thread t = new Thread(r, "pts-run-worker-sched");
        t.setDaemon(true);
        return t;
    });

    /** 并发闸门：串行化「停机标志 / 认领 / 提交 / 登记 Future」，停机时先加此锁再置位。 */
    private final ReentrantLock dispatchLock = new ReentrantLock();

    /** 已派发到运行线程池、尚未结束的任务，停机时等待其完成；任务结束后在 finally 中移除自身。 */
    private final Set<Future<?>> inFlight = ConcurrentHashMap.newKeySet();

    private volatile boolean running = false;
    private volatile boolean shuttingDown = false;

    public PromptTestSetRunWorkerScheduler(
            PromptTestSetService promptTestSetService,
            @Qualifier("promptTestSetRunExecutor") AsyncTaskExecutor runExecutor,
            @Value("${prompt-test-set.run.queue-enabled:false}") boolean queueEnabled,
            @Value("${prompt-test-set.run.poll-delay-ms:2000}") long pollDelayMs,
            @Value("${prompt-test-set.run.batch-size:5}") int batchSize,
            @Value("${prompt-test-set.run.recovery-delay-ms:30000}") long recoveryDelayMs,
            @Value("${prompt-test-set.run.stale-running-minutes:30}") long staleRunningMinutes,
            @Value("${prompt-test-set.run.shutdown-timeout-ms:30000}") long shutdownTimeoutMs) {
        this.promptTestSetService = promptTestSetService;
        this.runExecutor = runExecutor;
        this.queueEnabled = queueEnabled;
        this.pollDelayMs = pollDelayMs;
        this.batchSize = batchSize;
        this.recoveryDelayMs = recoveryDelayMs;
        this.staleRunningMinutes = staleRunningMinutes;
        this.shutdownTimeoutMs = Math.max(0, shutdownTimeoutMs);
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        if (!queueEnabled) {
            log.info("Prompt test set run queue disabled — async batch execution off");
            return;
        }
        startScheduling();
    }

    /** 启动轮询与恢复任务（包级可见，便于测试直接驱动）。 */
    void startScheduling() {
        log.info("Prompt test set run worker scheduler starting: pollDelay={}ms recoveryDelay={}ms",
                pollDelayMs, recoveryDelayMs);
        shuttingDown = false;
        running = true;
        scheduler.scheduleWithFixedDelay(this::pollAndDispatch, 1, pollDelayMs, TimeUnit.MILLISECONDS);
        scheduler.scheduleWithFixedDelay(this::recoverStaleRuns, 30, recoveryDelayMs, TimeUnit.MILLISECONDS);
    }

    // ── SmartLifecycle ────────────────────────────────────────────────

    /** 调度启动由 {@link ApplicationReadyEvent} 触发（{@link #startScheduling()}），此处不自动启动。 */
    @Override
    public void start() {
    }

    /** Spring 关闭时调用：停止轮询并等待已提交任务在限定时间内结束。 */
    @Override
    public void stop() {
        stopScheduling();
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return false;
    }

    @Override
    public int getPhase() {
        return SHUTDOWN_PHASE;
    }

    /**
     * 优雅停机（幂等，可在未启动时安全调用）：在 {@link #dispatchLock} 下设置停机标志并关闭调度池，
     * 再在超时窗口内等待已提交任务完成；保持该锁至置位完成，确保停机后不会再有派发周期认领/提交。
     */
    void stopScheduling() {
        dispatchLock.lock();
        try {
            if (running) {
                shuttingDown = true;
                scheduler.shutdown();
                log.info("Prompt test set run worker scheduler stopping — awaiting up to {}ms for {} in-flight run(s)",
                        shutdownTimeoutMs, inFlight.size());
                awaitInFlight();
                inFlight.clear();
                log.info("Prompt test run worker scheduler stopped");
            } else {
                scheduler.shutdown();
            }
        } finally {
            dispatchLock.unlock();
        }
        running = false;
    }

    private void awaitInFlight() {
        long deadline = System.currentTimeMillis() + shutdownTimeoutMs;
        for (Future<?> future : inFlight) {
            long remaining = deadline - System.currentTimeMillis();
            if (remaining <= 0) {
                log.warn("Prompt test set run worker shutdown timed out with {} in-flight task(s) still running; "
                        + "left-over running runs will be recovered on next startup", inFlight.size());
                return;
            }
            try {
                future.get(remaining, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                log.warn("Prompt test set run worker shutdown timed out waiting for in-flight tasks; "
                        + "left-over running runs will be recovered on next startup");
                return;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                log.warn("Prompt test set run worker shutdown interrupted while awaiting in-flight tasks");
                return;
            } catch (ExecutionException e) {
                log.debug("In-flight prompt test set run task finished with error", e.getCause());
            }
        }
    }

    private void pollAndDispatch() {
        dispatchLock.lock();
        try {
            if (shuttingDown) {
                return;
            }
            TenantContext.runAsSystem(() -> {
                List<PromptTestSetRun> queued = promptTestSetService.listQueuedRuns(batchSize);
                for (PromptTestSetRun run : queued) {
                    if (promptTestSetService.claimRun(run.getId())) {
                        // 先登记一个独立的 tracking Future，再提交任务。任务可能在 submit() 返回前就执行完成，
                        // 但其 finally 移除的是这个已预先登记的 tracking Future（不受提交时序影响），
                        // 避免了「任务已完成后仍把完成的 Future 重新加入 inFlight」的发布竞态。
                        CompletableFuture<Void> tracking = new CompletableFuture<>();
                        inFlight.add(tracking);
                        try {
                        runExecutor.submit(() -> {
                            try {
                                TenantContext.runAs(run.getTenantId(),
                                        () -> promptTestSetService.executeRun(run.getId()));
                            } finally {
                                inFlight.remove(tracking);
                                tracking.complete(null);
                            }
                        });
                        } catch (RejectedExecutionException e) {
                            // 停机过程中运行线程池已关闭——已认领的 run 交由 recovery 兜底
                            inFlight.remove(tracking);
                            log.warn("Run {} claimed but scheduler is shutting down — not dispatched, "
                                    + "left for recovery", run.getId());
                        }
                    }
                }
            });
        } catch (Exception e) {
            log.error("Prompt test set run worker polling error", e);
        } finally {
            dispatchLock.unlock();
        }
    }

    private void recoverStaleRuns() {
        try {
            promptTestSetService.markStaleRunsFailed(staleRunningMinutes);
        } catch (Exception e) {
            log.error("Prompt test set run recovery error", e);
        }
    }

    /** 当前仍在途（已派发但未全部结束）的任务数；测试验证用。 */
    int inFlightSize() {
        return inFlight.size();
    }
}