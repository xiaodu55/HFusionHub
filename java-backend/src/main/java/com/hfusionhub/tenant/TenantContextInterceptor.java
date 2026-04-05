package com.hfusionhub.tenant;

import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.Tenant;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.TenantMapper;
import com.hfusionhub.mapper.TenantMemberMapper;
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
 * <p>Tenant is a hard isolation boundary. For normal authenticated requests the
 * active tenant is derived ONLY from the login session + validated
 * {@code tenant_member} membership — a client-supplied {@code X-Tenant-Id} header
 * is IGNORED so a user cannot spoof another tenant.</p>
 *
 * <p>Resolution order:
 * <ol>
 *   <li>Authenticated user → {@code sys_user.tenant_id} (must be an active
 *       {@code tenant_member} of that tenant). Client {@code X-Tenant-Id} is
 *       ignored.</li>
 *   <li>Platform admin → an explicit {@code X-Target-Tenant} header selects a
 *       different tenant "on behalf of" a tenant. Requires {@code platform_admin};
 *       the target must exist and be {@code active} (else 404/403). Recorded in
 *       the tenant audit log.</li>
 *   <li>Unauthenticated internal callback (Python→Java) → {@code X-Tenant-Id}
 *       header, honoured ONLY on guarded, signature-verified callback routes.</li>
 * </ol></p>
 *
 * <p>In strict mode an unresolved tenant results in HTTP 403 (no default tenant).
 * A default tenant is applied ONLY in non-strict mode (tests).</p>
 *
 * <p>Registered at order 3 in {@code SaTokenConfig}, after auth (order 2).</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TenantContextInterceptor implements HandlerInterceptor {

    /** Callback path pattern, e.g. {@code /vectorize/{documentId}/callback}. */
    static final String CALLBACK_PATH_PREFIX = "/vectorize/";
    static final String CALLBACK_PATH_SUFFIX = "/callback";

    /** Request attribute set by {@link CallbackSignatureFilter} after verification. */
    static final String CALLBACK_VERIFIED_ATTR = "hfusionhub.callback.verified";

    private final UserMapper userMapper;
    private final TenantMemberMapper tenantMemberMapper;
    private final TenantMapper tenantMapper;

    @Value("${hfusionhub.tenant.strict:true}")
    private boolean strict;

    @Value("${hfusionhub.tenant.default-tenant-id:1}")
    private Long defaultTenantId;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response,
                             Object handler) {

        // 1. Authenticated user request — tenant comes from login + validated membership.
        if (JwtUtils.isLogin()) {
            try {
                Long userId = JwtUtils.getCurrentUserId();
                User user = userMapper.selectById(userId);
                if (user == null) {
                    return rejectNoTenant(request, response);
                }

                // 1a. Platform admin may act on behalf of an explicit target tenant.
                String targetTenant = request.getHeader("X-Target-Tenant");
                if (Boolean.TRUE.equals(user.getPlatformAdmin())
                        && targetTenant != null && !targetTenant.isBlank()) {
                    return resolveTargetTenant(user, targetTenant, request, response);
                }

                // 1b. User's own tenant, validated against tenant_member membership.
                if (!isActiveMember(user.getTenantId(), userId)) {
                    log.warn("User {} is not an active member of tenant {}", userId, user.getTenantId());
                    return rejectNoTenant(request, response);
                }
                TenantContext.setTenantId(user.getTenantId());
                return true;
            } catch (Exception e) {
                log.warn("Could not resolve tenant from authenticated user: {}", e.getMessage());
                return rejectNoTenant(request, response);
            }
        }

        // 2. Unauthenticated request.  X-Tenant-Id is ONLY trusted on guarded
        //    callback routes whose signature has already been verified by the
        //    CallbackSignatureFilter (set as a request attribute).  Any other
        //    unauthenticated request is rejected in strict mode — never does an
        //    unverified client control the tenant context.
        if (isCallbackPath(request) && Boolean.TRUE.equals(
                request.getAttribute(CALLBACK_VERIFIED_ATTR))) {
            String headerTenant = request.getHeader("X-Tenant-Id");
            if (headerTenant != null && !headerTenant.isBlank()) {
                try {
                    TenantContext.setTenantId(Long.parseLong(headerTenant));
                    return true;
                } catch (NumberFormatException e) {
                    log.warn("Invalid X-Tenant-Id header on callback: {}", headerTenant);
                }
            }
            // A verified callback may omit X-Tenant-Id. The callback service
            // derives the authoritative tenant from the document ownership
            // chain before it performs tenant-scoped work. Do not require a
            // caller-controlled header merely to enter that bootstrap path.
            return true;
        }

        // 3. Default tenant only in non-strict mode (e.g. tests)
        if (!strict) {
            TenantContext.setTenantId(defaultTenantId);
            return true;
        }

        // Strict mode: no tenant resolved → fail closed.
        return rejectNoTenant(request, response);
    }

    /**
     * Resolve a platform-admin cross-tenant override.
     *
     * <p>This does NOT silently fall back to the caller's own tenant.  A
     * malformed header yields 403; a well-formed id that does not name an
     * existing, {@code active} tenant yields 404.</p>
     */
    private boolean resolveTargetTenant(User user, String targetTenant,
                                        HttpServletRequest request,
                                        HttpServletResponse response) {
        Long target;
        try {
            target = Long.parseLong(targetTenant);
        } catch (NumberFormatException e) {
            log.warn("Invalid X-Target-Tenant header: {}", targetTenant);
            return rejectWithStatus(response, HttpServletResponse.SC_FORBIDDEN,
                    "Invalid X-Target-Tenant header");
        }
        if (target == null || target < 1) {
            log.warn("Invalid X-Target-Tenant value: {}", targetTenant);
            return rejectWithStatus(response, HttpServletResponse.SC_FORBIDDEN,
                    "Invalid X-Target-Tenant value");
        }

        Tenant tenant;
        try {
            tenant = tenantMapper.selectById(target);
        } catch (Exception e) {
            log.warn("Target tenant lookup failed for {}: {}", target, e.getMessage());
            return rejectWithStatus(response, HttpServletResponse.SC_INTERNAL_SERVER_ERROR,
                    "Tenant resolution failed");
        }
        if (tenant == null || !"active".equalsIgnoreCase(tenant.getStatus())) {
            log.warn("X-Target-Tenant {} does not exist or is not active", target);
            return rejectWithStatus(response, HttpServletResponse.SC_NOT_FOUND,
                    "Target tenant not found or inactive");
        }

        TenantContext.setTenantId(target);
        TenantContext.setCrossTenant(true);
        TenantContext.logCrossTenant(user.getId(), user.getTenantId(), target,
                request.getMethod() + " " + request.getRequestURI());
        return true;
    }

    /** True when the URI matches the guarded callback pattern (e.g. /vectorize/{id}/callback). */
    private boolean isCallbackPath(HttpServletRequest request) {
        // getServletPath() is relative to the context path (e.g. /api), so the
        // guard is robust regardless of server.servlet.context-path.
        String path = request.getServletPath();
        if (path == null) {
            path = request.getRequestURI();
        }
        if (path == null || path.length() < (CALLBACK_PATH_PREFIX.length() + CALLBACK_PATH_SUFFIX.length())) {
            return false;
        }
        return path.startsWith(CALLBACK_PATH_PREFIX) && path.endsWith(CALLBACK_PATH_SUFFIX);
    }

    private boolean isActiveMember(Long tenantId, Long userId) {
        if (tenantId == null) {
            return false;
        }
        try {
            TenantMember member = tenantMemberMapper.selectByTenantAndUser(tenantId, userId);
            return member != null;
        } catch (Exception e) {
            log.warn("Membership check failed: {}", e.getMessage());
            return false;
        }
    }

    private boolean rejectNoTenant(HttpServletRequest request, HttpServletResponse response) {
        log.warn("No tenant resolved for request: {} {} (strict mode)",
                 request.getMethod(), request.getRequestURI());
        if (strict) {
            return rejectWithStatus(response, HttpServletResponse.SC_FORBIDDEN,
                    "Tenant context required but not resolved");
        }
        TenantContext.setTenantId(defaultTenantId);
        return true;
    }

    private boolean rejectWithStatus(HttpServletResponse response, int status, String message) {
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        try {
            response.getWriter().write("{\"code\":" + status + ",\"message\":\"" + message + "\"}");
        } catch (Exception ignored) {}
        return false;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response,
                                Object handler, Exception ex) {
        TenantContext.clear();
    }
}
