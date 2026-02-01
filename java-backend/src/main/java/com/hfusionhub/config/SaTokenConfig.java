package com.hfusionhub.config;

import cn.dev33.satoken.interceptor.SaInterceptor;
import cn.dev33.satoken.router.SaRouter;
import cn.dev33.satoken.stp.StpUtil;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Sa-Token 配置
 *
 * @author HFusionHub Team
 */
@Configuration
public class SaTokenConfig implements WebMvcConfigurer {

    /**
     * 注册 Sa-Token 拦截器
     *
     * @param registry 拦截器注册表
     */
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new SaInterceptor(handle -> {
            // 登录验证 - 除登录接口外，其他接口都需要登录
            SaRouter.match("/api/**")
                    .notMatch(
                            "/api/user/login",
                            "/api/user/register",
                            "/api/doc.html",
                            "/api/swagger-ui/**",
                            "/api/v3/api-docs/**",
                            "/api/webjars/**"
                    )
                    .check(r -> StpUtil.checkLogin());
        })).addPathPatterns("/api/**");
    }
}
