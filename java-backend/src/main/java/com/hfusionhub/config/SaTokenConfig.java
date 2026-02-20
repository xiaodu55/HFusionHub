package com.hfusionhub.config;

import cn.dev33.satoken.interceptor.SaInterceptor;
import cn.dev33.satoken.router.SaRouter;
import cn.dev33.satoken.stp.StpUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Sa-Token 配置 — 认证拦截器 + 登录限流拦截器
 *
 * @author HFusionHub Team
 */
@Configuration
@RequiredArgsConstructor
public class SaTokenConfig implements WebMvcConfigurer {

    private final LoginRateLimitInterceptor loginRateLimitInterceptor;

    /**
     * 注册拦截器链：限流（order 1）→ 认证（order 2）
     *
     * @param registry 拦截器注册表
     */
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Rate-limit interceptor — runs BEFORE auth to reject locked-out IPs early
        registry.addInterceptor(loginRateLimitInterceptor)
                .addPathPatterns("/user/login", "/user/register")
                .order(1);

        // Sa-Token authentication interceptor
        // Spring removes server.servlet.context-path before interceptor
        // matching.  These patterns must therefore be relative to /api.
        registry.addInterceptor(new SaInterceptor(handle -> {
            SaRouter.match("/**")
                    .notMatch(
                            "/user/login",
                            "/user/register",
                            "/health",
                            "/vectorize/*/callback",
                            "/doc.html",
                            "/swagger-ui.html",
                            "/swagger-ui/**",
                            "/v3/api-docs/**",
                            "/webjars/**"
                    )
                    .check(r -> StpUtil.checkLogin());
        })).addPathPatterns("/**").order(2);
    }
}
