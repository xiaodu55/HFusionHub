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

    private TenantContext() {}

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
            throw new IllegalStateException(
                "No tenant context set. Ensure TenantContextInterceptor is registered " +
                "or wrap the call with TenantContext.runAs().");
        }
        return id;
    }

    /** Clear the tenant context (called after request completion). */
    public static void clear() {
        TENANT_HOLDER.remove();
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
