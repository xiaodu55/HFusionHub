package com.hfusionhub.config;

import java.util.Map;
import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

/**
 * 线程池配置
 *
 * @author HFusionHub Team
 */
@Configuration
public class ThreadPoolConfig {

    /**
     * SSE 流式响应线程池。
     * <p>容量模型：每个流式转发任务从提交起占用一个线程直到流结束（秒级到
     * 分钟级），因此核心线程数必须对齐目标并发流数，而非 CPU 核数。JDK 线程池
     * 是「先填满队列再扩到 max」——旧参数 core5/queue100 在 50+ 并发流时只有
     * 5 个流真正在跑、其余全部排队，正是 k6 爬坡 100 VU 拐点（P95 3018ms）的
     * 主因；现改为 core≈并发目标、小队列、空闲线程 120s 回收。</p>
     * <p>注意：不能用虚拟线程执行器——任务从请求线程提交到该执行器时，
     * 虚拟线程不继承父线程的普通 ThreadLocal，Sa-Token/租户上下文会丢失
     * （表现为流式对话 NotLoginException、无内容）。平台线程池 + CallerRunsPolicy
     * 保持请求线程的 ThreadLocal 语义，是 SSE 转发链路的正确选择；饱和时
     * CallerRuns 让提交线程自己执行流转发，属可接受的过载背压。</p>
     */
    @Bean("sseTaskExecutor")
    public Executor sseTaskExecutor(
            @Value("${app.sse.executor.core-pool-size:32}") int corePoolSize,
            @Value("${app.sse.executor.max-pool-size:64}") int maxPoolSize,
            @Value("${app.sse.executor.queue-capacity:32}") int queueCapacity) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(corePoolSize);
        executor.setMaxPoolSize(maxPoolSize);
        executor.setQueueCapacity(queueCapacity);
        executor.setKeepAliveSeconds(120);
        executor.setAllowCoreThreadTimeOut(true);
        executor.setThreadNamePrefix("sse-");
        executor.setTaskDecorator(new MdcPropagationDecorator());
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        executor.initialize();
        return executor;
    }

    /**
     * Agent Worker 线程池 — 异步执行 Agent 任务
     */
    @Bean("agentWorkerExecutor")
    public Executor agentWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("agent-worker-");
        executor.setTaskDecorator(new MdcPropagationDecorator());
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        executor.initialize();
        return executor;
    }

    /**
     * 提示词测试用例集批量运行 Worker 线程池 — 异步执行批量评测任务
     */
    @Bean("promptTestSetRunExecutor")
    public ThreadPoolTaskExecutor promptTestSetRunExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("pts-run-");
        executor.setTaskDecorator(new MdcPropagationDecorator());
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        executor.initialize();
        return executor;
    }

    /**
     * 后台杂务线程池 — fire-and-forget 异步任务（如会话删除后的记忆固化）。
     * 自定义 Executor Bean 存在时 Boot 的 applicationTaskExecutor 会退避，
     * 无限定符的 @Async 会落到每任务新建线程的 SimpleAsyncTaskExecutor（无上界）；
     * 这里有界池 + CallerRunsPolicy 兜住这类调用。
     */
    @Bean("housekeepingExecutor")
    public Executor housekeepingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("housekeeping-");
        executor.setTaskDecorator(new MdcPropagationDecorator());
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }

    /**
     * 把提交线程的 MDC（trace_id 等）带进池内线程：异步任务日志不再丢
     * trace 链。提交时无 MDC（如 @Scheduled 入口）则为无操作；恢复原值
     * 而非直接 clear，防池内线程嵌套装饰时误删外层上下文。
     */
    static final class MdcPropagationDecorator implements TaskDecorator {

        @Override
        public Runnable decorate(Runnable runnable) {
            Map<String, String> submitted = MDC.getCopyOfContextMap();
            return () -> {
                Map<String, String> previous = MDC.getCopyOfContextMap();
                if (submitted != null) {
                    MDC.setContextMap(submitted);
                }
                try {
                    runnable.run();
                } finally {
                    if (previous != null) {
                        MDC.setContextMap(previous);
                    } else {
                        MDC.clear();
                    }
                }
            };
        }
    }
}
