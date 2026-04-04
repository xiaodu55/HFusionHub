package com.hfusionhub.tenant;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Unit tests for {@link TenantContext} — the fail-closed tenant scope primitive.
 */
class TenantContextTest {

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    @Test
    void requireTenantIdThrowsWhenNoContext() {
        assertThrows(IllegalStateException.class, TenantContext::requireTenantId);
    }

    @Test
    void requireTenantIdReturnsSetValue() {
        TenantContext.setTenantId(7L);
        assertEquals(7L, TenantContext.requireTenantId());
    }

    @Test
    void runAsScopesBodyAndRestoresPrevious() {
        TenantContext.setTenantId(1L);
        AtomicLong inside = new AtomicLong();
        TenantContext.runAs(9L, () -> inside.set(TenantContext.requireTenantId()));
        assertEquals(9L, inside.get());
        assertEquals(1L, TenantContext.requireTenantId());
    }

    @Test
    void runAsVoidOverload() {
        AtomicLong seen = new AtomicLong();
        TenantContext.runAs(3L, () -> seen.set(TenantContext.getTenantId()));
        assertEquals(3L, seen.get());
        assertNull(TenantContext.getTenantId());
    }

    @Test
    void runAsSystemSkipsTenantRequirement() {
        TenantContext.runAsSystem(() -> {
            assertTrue(TenantContext.isSystemScope());
            // No tenant set — must not throw under system scope.
            assertNull(TenantContext.getTenantId());
        });
        assertFalse(TenantContext.isSystemScope());
    }

    @Test
    void runAsSystemVoidOverload() {
        AtomicLong ran = new AtomicLong();
        TenantContext.runAsSystem(() -> ran.incrementAndGet());
        assertEquals(1L, ran.get());
        assertFalse(TenantContext.isSystemScope());
    }

    @Test
    void runAsSystemRestoresOuterScope() {
        TenantContext.setTenantId(5L);
        TenantContext.runAsSystem(() -> assertTrue(TenantContext.isSystemScope()));
        assertFalse(TenantContext.isSystemScope());
        assertEquals(5L, TenantContext.requireTenantId());
    }

    @Test
    void clearRemovesAllScopes() {
        TenantContext.setTenantId(1L);
        TenantContext.setCrossTenant(true);
        TenantContext.runAsSystem(() -> {
            TenantContext.clear();
            assertNull(TenantContext.getTenantId());
            assertFalse(TenantContext.isCrossTenant());
            assertFalse(TenantContext.isSystemScope());
        });
        assertFalse(TenantContext.isSystemScope());
    }
}
