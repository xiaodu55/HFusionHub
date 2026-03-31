package com.hfusionhub.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Servlet filter that propagates {@code X-Trace-ID} through every request.
 *
 * <p>Behaviour:</p>
 * <ol>
 *   <li>Extract {@code X-Trace-ID} from the incoming request header.</li>
 *   <li>If absent, generate a new UUID-based trace ID.</li>
 *   <li>Install the trace ID into SLF4J MDC ({@link TraceContext}) so all
 *       log lines in this thread carry it.</li>
 *   <li>Add {@code X-Trace-ID} to the response header so the frontend can
 *       correlate client-side logs with server-side logs.</li>
 *   <li>Clear MDC in {@code finally} to avoid leakage across pooled threads.</li>
 * </ol>
 *
 * <p>This filter runs with the highest precedence (lowest order value) so that
 * the trace ID is available to all downstream filters, interceptors, and
 * controllers.</p>
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String traceId = request.getHeader(TraceContext.HEADER_NAME);
        if (traceId == null || traceId.isBlank()) {
            traceId = TraceContext.create();
        } else {
            TraceContext.set(traceId);
        }

        response.setHeader(TraceContext.HEADER_NAME, traceId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            TraceContext.clear();
        }
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        // Health probes and static assets do not need trace propagation
        return path.equals("/api/health")
                || path.equals("/api/ready")
                || path.startsWith("/doc.html")
                || path.startsWith("/swagger-ui")
                || path.startsWith("/v3/api-docs")
                || path.startsWith("/webjars");
    }
}
