package com.hfusionhub.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.StringUtils;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

/**
 * 跨域配置
 *
 * <p>开发/内网穿透场景（cpolar 等）的 Origin 是动态域名，无法枚举白名单；
 * 默认放行任意 Origin（allowedOriginPatterns("*")）。生产环境应通过
 * {@code app.cors.allowed-origins}（逗号分隔）配置固定域名收紧，并将
 * {@code app.cors.allow-any-origin} 置为 {@code false}——届时未配置白名单的
 * 部署不会回退到全放行，CORS 直接不生效（同源限制），避免任意 Origin 带
 * 凭据调用。</p>
 *
 * @author HFusionHub Team
 */
@Configuration
@Slf4j
public class CorsConfig {

    /**
     * 允许跨域请求的来源（逗号分隔；留空时由 allow-any-origin 决定行为）
     */
    @Value("${app.cors.allowed-origins:}")
    private String allowedOrigins;

    /**
     * 未配置白名单时是否放行任意 Origin（第十五轮 P0-8 起默认 false：通配
     * Origin + allowCredentials 组合是生产安全隐患）。开发/内网穿透场景需
     * 显式设置 app.cors.allow-any-origin=true；生产配置 allowed-origins 白名单。
     */
    @Value("${app.cors.allow-any-origin:false}")
    private boolean allowAnyOrigin;

    /**
     * 允许的请求方法
     */
    private static final String[] ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"};

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
        "Access-Control-Request-Headers",
        "satoken"
    };

    /**
     * 暴露的响应头
     */
    private static final String[] EXPOSED_HEADERS = {"Authorization", "Content-Type", "satoken"};

    /**
     * CORS 过滤器
     *
     * @return CORS 过滤器
     */
    @Bean
    public CorsFilter corsFilter() {
        CorsConfiguration config = new CorsConfiguration();

        // 允许的来源：配置了 app.cors.allowed-origins 则用白名单；
        // 否则仅在 allow-any-origin=true（开发/内网穿透）时放行任意 Origin，
        // 生产未配置白名单时 CORS 不生效（等同源限制），杜绝凭据跨域泄露。
        if (StringUtils.hasText(allowedOrigins)) {
            for (String origin : allowedOrigins.split(",")) {
                String trimmed = origin.trim();
                if (StringUtils.hasText(trimmed)) {
                    config.addAllowedOriginPattern(trimmed);
                }
            }
        } else if (allowAnyOrigin) {
            // 开发/内网穿透（cpolar 动态域名）：显式选择放行任意 Origin。
            // 通配 Origin + allowCredentials=true 会允许任意站点带凭据跨域调用，
            // 生产环境必须改用 allowed-origins 白名单——此处大声告警以便审计。
            log.warn("CORS allow-any-origin=true：任意 Origin 均可携带凭据跨域调用，"
                    + "生产环境请配置 app.cors.allowed-origins 白名单并关闭该项");
            config.addAllowedOriginPattern("*");
        } else {
            // 生产未配置白名单：注册空配置（仅放行同源），不放开任何跨域
            return new CorsFilter(new UrlBasedCorsConfigurationSource());
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
