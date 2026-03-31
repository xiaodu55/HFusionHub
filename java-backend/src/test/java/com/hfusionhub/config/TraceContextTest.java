package com.hfusionhub.config;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Unit tests for {@link TraceContext}.
 */
class TraceContextTest {

    @Test
    void createShouldGenerateNonEmptyId() {
        String id = TraceContext.create();
        assertNotNull(id);
        assertFalse(id.isBlank());
        assertFalse(id.contains("-"), "trace ID should not contain dashes");
        assertEquals(id, MDC.get(TraceContext.MDC_KEY));
    }

    @Test
    void setShouldInstallIdIntoMDC() {
        String id = TraceContext.set("my-trace-123");
        assertEquals("my-trace-123", id);
        assertEquals("my-trace-123", TraceContext.getTraceId());
    }

    @Test
    void getTraceIdShouldReturnNullWhenNotSet() {
        TraceContext.clear();
        assertNull(TraceContext.getTraceId());
    }

    @Test
    void getOrCreateShouldGenerateWhenAbsent() {
        TraceContext.clear();
        String id = TraceContext.getOrCreate();
        assertNotNull(id);
        assertEquals(id, TraceContext.getTraceId());
    }

    @Test
    void getOrCreateShouldReturnExistingWhenPresent() {
        TraceContext.set("existing-id");
        String id = TraceContext.getOrCreate();
        assertEquals("existing-id", id);
    }

    @Test
    void clearShouldRemoveFromMDC() {
        TraceContext.set("to-be-cleared");
        assertNotNull(TraceContext.getTraceId());
        TraceContext.clear();
        assertNull(TraceContext.getTraceId());
    }

    @Test
    void createShouldOverwriteExistingMDC() {
        TraceContext.set("old-id");
        String newId = TraceContext.create();
        assertNotEquals("old-id", newId);
        assertEquals(newId, TraceContext.getTraceId());
    }

    @Test
    void headerNameShouldBeXTraceID() {
        assertEquals("X-Trace-ID", TraceContext.HEADER_NAME);
    }
}
