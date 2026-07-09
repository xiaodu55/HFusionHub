package com.hfusionhub.config;

import cn.dev33.satoken.interceptor.SaInterceptor;
import cn.dev33.satoken.router.SaRouter;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.tenant.TenantContextInterceptor;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Sa-Token 配置 — 认证拦截器 + 登录限流拦截器 + 租户上下文
 *
 * @author HFusionHub Team
 */
@Configuration
@RequiredArgsConstructor
public class SaTokenConfig implements WebMvcConfigurer {

    private final LoginRateLimitInterceptor loginRateLimitInterceptor;
    private final TenantContextInterceptor tenantContextInterceptor;

    /**
     * 注册拦截器链：限流（1）→ 认证（2）→ 租户上下文（3）
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
                                    "/internal/feature-flags/snapshot",
                                    "/internal/eval-harness/**",
                                    "/internal/agent/**",
                                    "/internal/plugin/**",
                                    "/internal/notes/**",
                                    "/internal/memory/**",
                                    "/openapi/**",
                                    "/doc.html",
                                    "/swagger-ui.html",
                                    "/swagger-ui/**",
                                    "/v3/api-docs/**",
                                    "/webjars/**")
                            .check(r -> StpUtil.checkLogin());

                    // Newly registered accounts may log in and inspect their account state,
                    // but cannot access any business capability until the sole super admin
                    // assigns an approved platform role.
                    SaRouter.match("/**")
                            .notMatch(
                                    "/user/**",
                                    "/health",
                                    "/vectorize/*/callback",
                                    "/internal/**",
                                    "/openapi/**",
                                    "/doc.html",
                                    "/swagger-ui.html",
                                    "/swagger-ui/**",
                                    "/v3/api-docs/**",
                                    "/webjars/**")
                            .check(r -> {
                                boolean approved = StpUtil.hasRole(CommonConstants.ROLE_USER)
                                        || StpUtil.hasRole(CommonConstants.ROLE_BUILDER)
                                        || StpUtil.hasRole(CommonConstants.ROLE_ADMIN);
                                if (!approved) {
                                    throw new BusinessException(StatusCode.FORBIDDEN, "账号正在等待管理员分配身份，暂时不能使用业务功能");
                                }
                            });
                }))
                .addPathPatterns("/**")
                .order(2);

        // Tenant context — runs AFTER auth so we can resolve the user's tenant.
        // Only business routes participate.  Infrastructure/certuration routes
        // (/health, /user/login, /user/register, Swagger, internal feature-flag
        // snapshot) carry no tenant context and must NOT be rejected in strict
        // mode.  Callback routes stay intercepted so X-Tenant-Id is honoured
        // for the guarded Python->Java vectorize callback.
        registry.addInterceptor(tenantContextInterceptor)
                .addPathPatterns("/**")
                .excludePathPatterns(
                        "/health",
                        "/user/login",
                        "/user/register",
                        "/user/sso/**",
                        "/internal/eval-harness/**",
                        "/doc.html",
                        "/swagger-ui.html",
                        "/swagger-ui/**",
                        "/v3/api-docs/**",
                        "/webjars/**",
                        "/internal/feature-flags/snapshot",
                        "/internal/agent/**",
                        "/internal/plugin/**",
                        "/internal/notes/**",
                        "/openapi/**")
                .order(3);
    }
}
