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
}
