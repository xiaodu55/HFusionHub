package com.hfusionhub.config;

import io.netty.channel.ChannelOption;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

/**
 * WebClient 配置 - 用于流式请求
 *
 * <p>Adds explicit timeouts (previously none — a hung upstream would hold the
 * SSE stream open indefinitely):
 * <ul>
 *   <li>connect timeout: 5s</li>
 *   <li>response timeout: 300s — matches the {@code SseEmitter} 300s hard
 *       timeout on the Java side, so long-running streaming responses are
 *       bounded by the same budget as the emitter, never longer.</li>
 * </ul>
 * </p>
 *
 * <p>The Reactor Netty client keeps a pooled connection to the Python AI
 * service and reuses it across requests.</p>
 *
 * @author HFusionHub Team
 */
@Configuration
public class WebClientConfig {

    /**
     * 连接超时（毫秒）
     */
    private static final int CONNECT_TIMEOUT_MS = 5000;

    /**
     * 响应超时 — 与 SseEmitter 300s 硬超时保持一致
     */
    private static final Duration RESPONSE_TIMEOUT = Duration.ofSeconds(300);

    @Bean
    public WebClient webClient() {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, CONNECT_TIMEOUT_MS)
                .responseTimeout(RESPONSE_TIMEOUT);
        return WebClient.builder()
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .codecs(configurer -> configurer.defaultCodecs().maxInMemorySize(10 * 1024 * 1024)) // 10MB
                .build();
    }
}
