package com.hfusionhub.tenant;

import java.util.function.Supplier;

/**
 * Thread-local holder for the current tenant ID.
 *
 * <p>Set by {@link TenantContextInterceptor} at the start of each HTTP request,
 * cleared in {@code afterCompletion}.  Mirrors the pattern of
 * {@link com.hfusionhub.config.TraceContext}.</p>
 *
 * <p>Scheduled jobs and async workers MUST wrap tenant-scoped work with
 * {@link #runAs(Long, Supplier)}.</p>
 *
 * @author HFusionHub Team
 */
public final class TenantContext {

    private static final ThreadLocal<Long> TENANT_HOLDER = new ThreadLocal<>();
    private static final ThreadLocal<Boolean> CROSS_TENANT_HOLDER = new ThreadLocal<>();
    private static final ThreadLocal<Boolean> SYSTEM_SCOPE_HOLDER = new ThreadLocal<>();

    private TenantContext() {}

    /**
     * Run a block in "system" scope: the tenant-line SQL interceptor skips
     * tenant filtering for every table in this thread.  Used ONLY by
     * cross-tenant maintenance jobs (recovery, orphan cleanup, reconciliation)
     * that deliberately operate on every tenant's data.
     */
    public static <T> T runAsSystem(Supplier<T> action) {
        Boolean previous = SYSTEM_SCOPE_HOLDER.get();
        SYSTEM_SCOPE_HOLDER.set(Boolean.TRUE);
        try {
            return action.get();
        } finally {
            if (previous != null) {
                SYSTEM_SCOPE_HOLDER.set(previous);
            } else {
                SYSTEM_SCOPE_HOLDER.remove();
            }
        }
    }

    /** Convenience overload for void system-scope actions. */
    public static void runAsSystem(Runnable action) {
        runAsSystem(() -> {
            action.run();
            return null;
        });
    }

    /** True when the current thread is in cross-tenant system scope. */
    public static boolean isSystemScope() {
        return Boolean.TRUE.equals(SYSTEM_SCOPE_HOLDER.get());
    }

    /** Flag this thread as a platform-admin acting on behalf of another tenant. */
    public static void setCrossTenant(boolean crossTenant) {
        CROSS_TENANT_HOLDER.set(crossTenant);
    }

    /** True when the active request is a platform-admin cross-tenant override. */
    public static boolean isCrossTenant() {
        return Boolean.TRUE.equals(CROSS_TENANT_HOLDER.get());
    }

    /**
     * Record a platform-admin cross-tenant operation in the tenant audit log.
     * Uses {@code SpringContextHolder} so it works from interceptor scope.
     */
    public static void logCrossTenant(Long operatorId, Long fromTenant, Long toTenant, String action) {
        try {
            var mapper = com.hfusionhub.common.utils.SpringContextHolder.getBean(
                    com.hfusionhub.mapper.TenantAuditLogMapper.class);
            mapper.insertCrossTenant(operatorId, fromTenant, toTenant, action);
        } catch (Exception e) {
            org.slf4j.LoggerFactory.getLogger(TenantContext.class)
                    .warn("Failed to record cross-tenant audit: {}", e.getMessage());
        }
    }

    /** Set the current tenant ID for this thread. */
    public static void setTenantId(Long tenantId) {
        TENANT_HOLDER.set(tenantId);
    }

    /** Get the current tenant ID, or null if not set. */
    public static Long getTenantId() {
        return TENANT_HOLDER.get();
    }

    /** Get the current tenant ID, throwing if absent. */
    public static Long requireTenantId() {
        Long id = TENANT_HOLDER.get();
        if (id == null) {
            throw new IllegalStateException("No tenant context set. Ensure TenantContextInterceptor is registered "
                    + "or wrap the call with TenantContext.runAs().");
        }
        return id;
    }

    /** Clear the tenant context (called after request completion). */
    public static void clear() {
        TENANT_HOLDER.remove();
        CROSS_TENANT_HOLDER.remove();
        SYSTEM_SCOPE_HOLDER.remove();
    }

    /**
     * Execute a block of code as a specific tenant.
     * Used by scheduled jobs and async workers.
     */
    public static <T> T runAs(Long tenantId, Supplier<T> action) {
        Long previous = TENANT_HOLDER.get();
        TENANT_HOLDER.set(tenantId);
        try {
            return action.get();
        } finally {
            if (previous != null) {
                TENANT_HOLDER.set(previous);
            } else {
                TENANT_HOLDER.remove();
            }
        }
    }

    /** Convenience overload for void actions. */
    public static void runAs(Long tenantId, Runnable action) {
        runAs(tenantId, () -> {
            action.run();
            return null;
        });
    }
}
