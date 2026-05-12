package com.hfusionhub.config;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

/**
 * RestTemplate 配置
 *
 * <p>Uses {@link RestTemplateBuilder} so Spring Boot's auto-configured
 * {@link com.fasterxml.jackson.databind.ObjectMapper} (with
 * FAIL_ON_UNKNOWN_PROPERTIES=false) is injected into the message converter.
 * This prevents deserialisation failures when the Python AI service adds
 * new JSON fields that the Java DTO does not yet know about.</p>
 *
 * <p>Transport: {@link JdkClientHttpRequestFactory} (JDK 21 HttpClient)
 * instead of the default {@code SimpleClientHttpRequestFactory}, which creates
 * a brand-new TCP connection per request. The JDK HttpClient reuses
 * keep-alive connections (HTTP/1.1) and supports HTTP/2 multiplexing,
 * avoiding TLS+TCP handshake overhead on the hot chat path. No extra
 * dependency required.</p>
 *
 * <p>Timeouts are read from {@code ai-service.timeout} (default 120s), the
 * same value used by the SSE path, so a misconfigured YAML value cannot
 * silently fall back to a hardcoded default again.</p>
 *
 * @author HFusionHub Team
 */
@Configuration
public class RestTemplateConfig {

    /**
     * 连接超时（毫秒）— 默认 5s
     */
    private static final long DEFAULT_CONNECT_TIMEOUT_MS = 5000;

    @Bean
    public RestTemplate restTemplate(
            RestTemplateBuilder builder,
            @Value("${ai-service.timeout:120000}") long readTimeoutMs) {
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(DEFAULT_CONNECT_TIMEOUT_MS))
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(Duration.ofMillis(readTimeoutMs));
        // Supplier 形式：RequestFactory 按需懒创建（3.2 无实例重载）
        return builder.requestFactory(() -> factory).build();
    }
}
