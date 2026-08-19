package com.hfusionhub.config;

import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
     * <p>注意：不能用虚拟线程执行器——任务从请求线程提交到该执行器时，
     * 虚拟线程不继承父线程的普通 ThreadLocal，Sa-Token/租户上下文会丢失
     * （表现为流式对话 NotLoginException、无内容）。平台线程池 + CallerRunsPolicy
     * 保持请求线程的 ThreadLocal 语义，是 SSE 转发链路的正确选择。</p>
     */
    @Bean("sseTaskExecutor")
    public Executor sseTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(5);
        executor.setMaxPoolSize(20);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("sse-");
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
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }
}
