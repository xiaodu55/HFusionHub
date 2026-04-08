package com.hfusionhub.config;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

/**
 * Webhook 异步投递配置
 *
 * <p>开启全局 {@code @Async} 支持；提供 Webhook 专用线程池、重试调度器与
 * 投递用 RestTemplate（短读超时，避免投递拖慢调用方）。</p>
 *
 * @author HFusionHub Team
 */
@Configuration
@EnableAsync
public class WebhookConfig {

    /**
     * Webhook 事件监听线程池。
     * 线程设为守护线程：投递属于尽力而为的旁路动作，不阻塞 JVM 退出
     * （与重试调度器一致），也避免测试套件因非守护线程滞留 30 秒。
     */
    @Bean("webhookExecutor")
    public ThreadPoolTaskExecutor webhookExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(500);
        executor.setThreadFactory(runnable -> {
            Thread thread = new Thread(runnable, "webhook-");
            thread.setDaemon(true);
            return thread;
        });
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        executor.initialize();
        return executor;
    }

    /**
     * Webhook 重试调度器（指数退避 1m/5m/15m）
     */
    @Bean("webhookRetryScheduler")
    public ScheduledExecutorService webhookRetryScheduler() {
        return Executors.newScheduledThreadPool(2, runnable -> {
            Thread thread = new Thread(runnable, "webhook-retry");
            thread.setDaemon(true);
            return thread;
        });
    }

    /**
     * 投递用 RestTemplate：连接超时 5s，读超时 10s。
     * 与全局 RestTemplate（读超时 120s）区分，避免对不可达端点长时间等待。
     */
    @Bean("webhookRestTemplate")
    public RestTemplate webhookRestTemplate(RestTemplateBuilder builder) {
        return builder
                .setConnectTimeout(Duration.ofSeconds(5))
                .setReadTimeout(Duration.ofSeconds(10))
                .build();
    }
}
