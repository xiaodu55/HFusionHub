package com.hfusionhub.config;

import org.slf4j.MDC;

import java.util.UUID;

/**
 * Thread-local trace context propagated across Java→Python service calls.
 *
 * <p>The {@code trace_id} is either extracted from the incoming {@code X-Trace-ID}
 * header or generated fresh for each request.  It is placed into SLF4J MDC so
 * every log line from the same request carries the same correlation ID, and is
 * forwarded to the Python AI service via the {@code X-Trace-ID} HTTP header.</p>
 *
 * <p>Usage in controllers / services:</p>
 * <pre>
 *   String traceId = TraceContext.getTraceId();   // never null
 * </pre>
 */
public final class TraceContext {

    public static final String HEADER_NAME = "X-Trace-ID";
    public static final String MDC_KEY = "trace_id";

    private TraceContext() {}

    /**
     * Generate a new trace ID (UUID, no dashes) and install it into MDC.
     *
     * @return the generated trace ID
     */
    public static String create() {
        String id = UUID.randomUUID().toString().replace("-", "");
        MDC.put(MDC_KEY, id);
        return id;
    }

    /**
     * Install an existing trace ID into MDC (e.g. extracted from a header).
     *
     * @param traceId pre-existing trace ID (must not be null)
     * @return the same trace ID
     */
    public static String set(String traceId) {
        MDC.put(MDC_KEY, traceId);
        return traceId;
    }

    /**
     * Return the current trace ID from MDC, or {@code null} if none is set.
     */
    public static String getTraceId() {
        return MDC.get(MDC_KEY);
    }

    /**
     * Return the current trace ID, generating one if absent.
     */
    public static String getOrCreate() {
        String id = getTraceId();
        if (id == null || id.isBlank()) {
            id = create();
        }
        return id;
    }

    /**
     * Remove the trace ID from MDC.  Should be called in a {@code finally}
     * block to prevent MDC leakage across pooled threads.
     */
    public static void clear() {
        MDC.remove(MDC_KEY);
    }
}
