package com.hfusionhub.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

/**
 * 跨域配置
 *
 * @author HFusionHub Team
 */
@Configuration
public class CorsConfig {

    /**
     * 允许跨域请求的来源
     */
    private static final String[] ALLOWED_ORIGINS = {
            "http://localhost:5173",  // Vite 开发服务器
            "http://localhost:3000",  // 其他前端端口
            "http://localhost:8080",  // 前端部署端口
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000"
    };

    /**
     * 允许的请求方法
     */
    private static final String[] ALLOWED_METHODS = {
            "GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"
    };

    /**
     * 允许的请求头
     */
    private static final String[] ALLOWED_HEADERS = {
            "Authorization",
            "Content-Type",
            "X-Requested-With",
            "Accept",
            "Origin",
            "Access-Control-Request-Method",
            "Access-Control-Request-Headers"
    };

    /**
     * 暴露的响应头
     */
    private static final String[] EXPOSED_HEADERS = {
            "Authorization",
            "Content-Type"
    };

    /**
     * CORS 过滤器
     *
     * @return CORS 过滤器
     */
    @Bean
    public CorsFilter corsFilter() {
        CorsConfiguration config = new CorsConfiguration();

        // 允许的来源
        for (String origin : ALLOWED_ORIGINS) {
            config.addAllowedOrigin(origin);
        }

        // 允许的请求方法
        for (String method : ALLOWED_METHODS) {
            config.addAllowedMethod(method);
        }

        // 允许的请求头
        for (String header : ALLOWED_HEADERS) {
            config.addAllowedHeader(header);
        }

        // 暴露的响应头
        for (String header : EXPOSED_HEADERS) {
            config.addExposedHeader(header);
        }

        // 允许携带 Cookie
        config.setAllowCredentials(true);

        // 预检请求的有效期（秒）
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);

        return new CorsFilter(source);
    }
}
