package com.hfusionhub.config;

import java.time.Duration;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

/**
 * RestTemplate 配置
 *
 * Uses {@link RestTemplateBuilder} so Spring Boot's auto-configured
 * {@link com.fasterxml.jackson.databind.ObjectMapper} (with
 * FAIL_ON_UNKNOWN_PROPERTIES=false) is injected into the message converter.
 * This prevents deserialisation failures when the Python AI service adds
 * new JSON fields that the Java DTO does not yet know about.
 *
 * @author HFusionHub Team
 */
@Configuration
public class RestTemplateConfig {

    @Bean
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder
                .setConnectTimeout(Duration.ofSeconds(5))
                .setReadTimeout(Duration.ofSeconds(120))
                .build();
    }
}
