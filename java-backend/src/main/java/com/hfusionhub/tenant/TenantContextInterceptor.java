package com.hfusionhub.tenant;

import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.UserMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * HTTP interceptor that resolves the current tenant and sets {@link TenantContext}.
 *
 * <p>Resolution order:
 * <ol>
 *   <li>{@code X-Tenant-Id} header — used by internal (Python→Java) calls</li>
 *   <li>Authenticated user's {@code sys_user.tenant_id} — normal user requests</li>
 *   <li>Configured default tenant — only when {@code hfusionhub.tenant.strict=false}</li>
 * </ol>
 *
 * <p>Registered at order 3 in {@code SaTokenConfig}, after auth (order 2).</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TenantContextInterceptor implements HandlerInterceptor {

    private final UserMapper userMapper;

    @Value("${hfusionhub.tenant.strict:true}")
    private boolean strict;

    @Value("${hfusionhub.tenant.default-tenant-id:1}")
    private Long defaultTenantId;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response,
                             Object handler) {
        // 1. X-Tenant-Id header (internal / Python-to-Java calls)
        String headerTenant = request.getHeader("X-Tenant-Id");
        if (headerTenant != null && !headerTenant.isBlank()) {
            try {
                TenantContext.setTenantId(Long.parseLong(headerTenant));
                return true;
            } catch (NumberFormatException e) {
                log.warn("Invalid X-Tenant-Id header: {}", headerTenant);
            }
        }

        // 2. Authenticated user's tenant (normal user requests)
        try {
            if (JwtUtils.isLogin()) {
                Long userId = JwtUtils.getCurrentUserId();
                User user = userMapper.selectById(userId);
                if (user != null && user.getTenantId() != null) {
                    TenantContext.setTenantId(user.getTenantId());
                    return true;
                }
            }
        } catch (Exception e) {
            log.debug("Could not resolve tenant from authenticated user: {}", e.getMessage());
        }

        // 3. Default tenant (only in non-strict mode, e.g. tests)
        if (!strict) {
            TenantContext.setTenantId(defaultTenantId);
            return true;
        }

        // Strict mode: no tenant resolved → fail
        log.warn("No tenant resolved for request: {} {} (strict mode)",
                 request.getMethod(), request.getRequestURI());
        response.setStatus(403);
        response.setContentType("application/json;charset=UTF-8");
        try {
            response.getWriter().write(
                "{\"code\":403,\"message\":\"Tenant context required but not resolved\"}");
        } catch (Exception ignored) {}
        return false;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response,
                                Object handler, Exception ex) {
        TenantContext.clear();
    }
}
