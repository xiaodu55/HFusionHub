package com.hfusionhub.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;

/**
 * 线程池配置
 *
 * @author HFusionHub Team
 */
@Configuration
public class ThreadPoolConfig {

    /**
     * SSE 流式响应线程池。
     * <p>每个 SSE 连接会占用一个线程长达数分钟：JDK 21+ 优先使用虚拟线程
     * （每连接一个虚拟线程，不再受 20 线程上限约束），JDK 17 回退平台线程池。</p>
     */
    @Bean("sseTaskExecutor")
    public Executor sseTaskExecutor() {
        ExecutorService virtual = ExecutorSupport.newVirtualThreadPerTaskExecutor("sse");
        if (virtual != null) {
            return virtual;
        }
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
