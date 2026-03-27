package com.hfusionhub.scheduler;

import com.hfusionhub.entity.PromptTestSetRun;
import com.hfusionhub.service.PromptTestSetService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.task.AsyncTaskExecutor;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class PromptTestSetRunWorkerSchedulerTest {

    private PromptTestSetService service;
    private AsyncTaskExecutor runExecutor;
    private PromptTestSetRunWorkerScheduler scheduler;

    @AfterEach
    void tearDown() {
        if (scheduler != null) {
            scheduler.stopScheduling();
        }
    }

    /** 只构建对象并安装 mock，不启动调度；测试在装好 stub 后再显式调用 startScheduling() 避免首轮轮询竞争。 */
    private void buildScheduler(long shutdownTimeoutMs) {
        service = mock(PromptTestSetService.class);
        runExecutor = mock(AsyncTaskExecutor.class);
        scheduler = new PromptTestSetRunWorkerScheduler(
                service, runExecutor, true, 20, 5, 60_000, 30, shutdownTimeoutMs);
    }

    private PromptTestSetRun newRun(long id) {
        PromptTestSetRun run = new PromptTestSetRun();
        run.setId(id);
        return run;
    }

    private void awaitCondition(BooleanSupplier condition, long timeoutMs) throws Exception {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            if (condition.getAsBoolean()) {
                return;
            }
            Thread.sleep(20);
        }
        fail("condition not met within " + timeoutMs + "ms");
    }

    @FunctionalInterface
    private interface BooleanSupplier {
        boolean getAsBoolean();
    }

@Test
    void stopHaltsPolling() throws Exception {
        buildScheduler(5000);
        AtomicInteger polls = new AtomicInteger();
        when(service.listQueuedRuns(anyInt())).thenAnswer(inv -> {
            polls.incrementAndGet();
            return List.of();
        });
        scheduler.startScheduling();

        awaitCondition(() -> polls.get() >= 1, 3000);
        scheduler.stopScheduling();
        assertFalse(scheduler.isRunning());

        int stoppedAt = polls.get();
        Thread.sleep(200);
        assertEquals(stoppedAt, polls.get(), "polling must stop after graceful shutdown");
    }

    @Test
    void shutdownWaitsForInflightTasks() throws Exception {
        buildScheduler(5000);
        when(service.listQueuedRuns(anyInt())).thenReturn(List.of(newRun(1L)));
        when(service.claimRun(1L)).thenReturn(true, false);
        AtomicInteger submits = new AtomicInteger();
        CountDownLatch taskStarted = new CountDownLatch(1);
        CountDownLatch releaseTask = new CountDownLatch(1);
        when(runExecutor.submit(any(Runnable.class))).thenAnswer(inv -> {
            submits.incrementAndGet();
            Runnable task = inv.getArgument(0);
            CompletableFuture<Void> done = new CompletableFuture<>();
            Thread worker = new Thread(() -> {
                taskStarted.countDown();
                try {
                    releaseTask.await(10, TimeUnit.SECONDS);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                task.run();
                done.complete(null);
            }, "pts-sched-test-worker");
            worker.setDaemon(true);
            worker.start();
            return done;
        });
        scheduler.startScheduling();

        verify(service, timeout(3000).atLeastOnce()).claimRun(1L);
        awaitCondition(() -> taskStarted.getCount() == 0, 3000);

        CountDownLatch stopReturned = new CountDownLatch(1);
        AtomicLong stopElapsed = new AtomicLong();
        Thread stopper = new Thread(() -> {
            long start = System.currentTimeMillis();
            scheduler.stopScheduling();
            stopElapsed.set(System.currentTimeMillis() - start);
            stopReturned.countDown();
        }, "pts-sched-stopper");
        stopper.start();

        Thread.sleep(200);
        assertFalse(stopReturned.await(50, TimeUnit.MILLISECONDS),
                "stop must block while an in-flight task is still running");

        releaseTask.countDown();
        assertTrue(stopReturned.await(5, TimeUnit.SECONDS),
                "stop must return once the in-flight task finishes");
        stopper.join(1000);
        assertFalse(scheduler.isRunning());
        assertTrue(stopElapsed.get() >= 150, "stop should have waited for the in-flight task");
        assertEquals(1, submits.get());
    }

    @Test
    void shutdownTimesOutWhenTaskHangs() throws Exception {
        buildScheduler(400);
        when(service.listQueuedRuns(anyInt())).thenReturn(List.of(newRun(1L)));
        when(service.claimRun(1L)).thenReturn(true, false);
        when(runExecutor.submit(any(Runnable.class)))
                .thenReturn(new CompletableFuture<>());
        scheduler.startScheduling();

        verify(service, timeout(3000).atLeastOnce()).claimRun(1L);
        Thread.sleep(200); // 确保已提交并登记进 inFlight

        long start = System.currentTimeMillis();
        scheduler.stopScheduling();
        long elapsed = System.currentTimeMillis() - start;

        assertFalse(scheduler.isRunning());
        assertTrue(elapsed >= 300, "stop should wait for the shutdown timeout window");
        assertTrue(elapsed < 5000, "stop must not block forever when tasks hang");
    }

    @Test
void completedTasksDoNotAccumulateInInFlight() throws Exception {
        buildScheduler(400);
        when(service.listQueuedRuns(anyInt())).thenReturn(List.of(newRun(1L)));
        when(service.claimRun(1L)).thenReturn(true, false);
        when(runExecutor.submit(any(Runnable.class))).thenAnswer(inv -> {
            Runnable task = inv.getArgument(0);
            CompletableFuture<Void> done = new CompletableFuture<>();
            Thread worker = new Thread(() -> {
                task.run();               // 任务本身会移除自身 Future
                done.complete(null);
            }, "pts-sched-test-worker");
            worker.setDaemon(true);
            worker.start();
            return done;
        });
        scheduler.startScheduling();

        verify(service, timeout(3000).atLeastOnce()).claimRun(1L);
        verify(runExecutor, timeout(3000).atLeastOnce()).submit(any(Runnable.class));
        awaitCondition(() -> scheduler.inFlightSize() == 0, 3000);
    }

    @Test
    void synchronousExecutorCompletingBeforeSubmitReturnsDoesNotAccumulate() throws Exception {
        buildScheduler(5000);
        when(service.listQueuedRuns(anyInt())).thenReturn(List.of(newRun(1L)));
        when(service.claimRun(1L)).thenReturn(true, false);
        // 同步执行器：任务在 submit() 返回之前就同步执行完毕
        when(runExecutor.submit(any(Runnable.class))).thenAnswer(inv -> {
            Runnable task = inv.getArgument(0);
            task.run();
            return CompletableFuture.completedFuture(null);
        });
        scheduler.startScheduling();

        verify(service, timeout(3000).atLeastOnce()).claimRun(1L);
        awaitCondition(() -> scheduler.inFlightSize() == 0, 3000);
        assertEquals(0, scheduler.inFlightSize());
    }

    @Test
    void stopSerializesAgainstInProgressDispatch_noResidualSubmits() throws Exception {
        buildScheduler(5000);
        when(service.listQueuedRuns(anyInt())).thenReturn(List.of(newRun(1L)));

        AtomicInteger claims = new AtomicInteger();
        CountDownLatch claimEntered = new CountDownLatch(1);
        CountDownLatch releaseClaim = new CountDownLatch(1);
        when(service.claimRun(1L)).thenAnswer(inv -> {
            // 仅第一次认领会阻塞住派发（趁机持有 dispatchLock），后续轮询直接不再认领
            boolean first = claims.incrementAndGet() == 1;
            if (first) {
                claimEntered.countDown();
                if (!releaseClaim.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("claim not released in time");
                }
            }
            return first;
        });
        when(runExecutor.submit(any(Runnable.class))).thenAnswer(inv -> {
            Runnable task = inv.getArgument(0);
            CompletableFuture<Void> done = new CompletableFuture<>();
            Thread worker = new Thread(() -> {
                task.run();
                done.complete(null);
            }, "pts-sched-test-worker");
            worker.setDaemon(true);
            worker.start();
            return done;
        });
        scheduler.startScheduling();

        assertTrue(claimEntered.await(3, TimeUnit.SECONDS),
                "a dispatch should have started and hold the shared lock inside claimRun");

        Thread stopper = new Thread(() -> {
            try {
                scheduler.stopScheduling();
            } catch (Exception ignored) {
            }
        });
        stopper.start();
        Thread.sleep(150);
        // 在派发周期未结束期间，stop 必须阻塞等待 dispatchLock
        verify(runExecutor, times(0)).submit(any(Runnable.class));

        releaseClaim.countDown();
        stopper.join(3000);
        assertFalse(stopper.isAlive(), "stop must complete once the in-progress dispatch finishes");
        assertFalse(scheduler.isRunning());
        assertEquals(1, claims.get());
        // 停机标志在锁内置位后，不再有新的认领/提交
        verify(runExecutor, times(1)).submit(any(Runnable.class));
        assertTrue(scheduler.inFlightSize() == 0);
    }

    @Test
    void stopIsNoOpWhenNotStarted() {
        service = mock(PromptTestSetService.class);
        runExecutor = mock(AsyncTaskExecutor.class);
        scheduler = new PromptTestSetRunWorkerScheduler(
                service, runExecutor, true, 20, 5, 60_000, 30, 5000);

        assertFalse(scheduler.isRunning());
        scheduler.stopScheduling();
        assertFalse(scheduler.isRunning());
    }
}