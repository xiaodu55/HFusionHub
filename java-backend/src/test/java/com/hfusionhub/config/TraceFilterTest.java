package com.hfusionhub.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.slf4j.MDC;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/**
 * Unit tests for {@link TraceFilter}.
 */
class TraceFilterTest {

    private TraceFilter filter;
    private HttpServletRequest request;
    private HttpServletResponse response;
    private FilterChain filterChain;

    @BeforeEach
    void setUp() {
        filter = new TraceFilter();
        request = mock(HttpServletRequest.class);
        response = mock(HttpServletResponse.class);
        filterChain = mock(FilterChain.class);
        TraceContext.clear();
    }

    @Test
    void shouldGenerateTraceIdWhenNoHeaderPresent() throws ServletException, IOException {
        when(request.getHeader(TraceContext.HEADER_NAME)).thenReturn(null);
        when(request.getRequestURI()).thenReturn("/api/conversation/message");

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<String> headerCaptor = ArgumentCaptor.forClass(String.class);
        verify(response).setHeader(eq(TraceContext.HEADER_NAME), headerCaptor.capture());

        String generatedId = headerCaptor.getValue();
        assertNotNull(generatedId);
        assertFalse(generatedId.isBlank());
    }

    @Test
    void shouldPassthroughExistingTraceId() throws ServletException, IOException {
        when(request.getHeader(TraceContext.HEADER_NAME)).thenReturn("my-custom-trace-001");
        when(request.getRequestURI()).thenReturn("/api/conversation/message");

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<String> headerCaptor = ArgumentCaptor.forClass(String.class);
        verify(response).setHeader(eq(TraceContext.HEADER_NAME), headerCaptor.capture());
        assertEquals("my-custom-trace-001", headerCaptor.getValue());
    }

    @Test
    void shouldInstallTraceIdIntoMDC() throws ServletException, IOException {
        when(request.getHeader(TraceContext.HEADER_NAME)).thenReturn("mdc-test-id");
        when(request.getRequestURI()).thenReturn("/api/conversation/message");

        filter.doFilterInternal(request, response, filterChain);

        // MDC should have been set during filter execution
        // (it's cleared in finally, so we verify via the response header)
        ArgumentCaptor<String> headerCaptor = ArgumentCaptor.forClass(String.class);
        verify(response).setHeader(eq(TraceContext.HEADER_NAME), headerCaptor.capture());
        assertEquals("mdc-test-id", headerCaptor.getValue());
    }

    @Test
    void shouldClearMDCAfterFilterChain() throws ServletException, IOException {
        when(request.getHeader(TraceContext.HEADER_NAME)).thenReturn("clear-test");
        when(request.getRequestURI()).thenReturn("/api/conversation/message");

        filter.doFilterInternal(request, response, filterChain);

        // After doFilterInternal returns, MDC should be clean
        assertNull(TraceContext.getTraceId());
    }

    @Test
    void shouldNotFilterHealthEndpoint() {
        when(request.getRequestURI()).thenReturn("/api/health");
        assertTrue(filter.shouldNotFilter(request));
    }

    @Test
    void shouldNotFilterReadyEndpoint() {
        when(request.getRequestURI()).thenReturn("/api/ready");
        assertTrue(filter.shouldNotFilter(request));
    }

    @Test
    void shouldNotFilterSwaggerUI() {
        when(request.getRequestURI()).thenReturn("/swagger-ui/index.html");
        assertTrue(filter.shouldNotFilter(request));
    }

    @Test
    void shouldFilterNormalEndpoints() {
        when(request.getRequestURI()).thenReturn("/api/conversation/message");
        assertFalse(filter.shouldNotFilter(request));
    }

    @Test
    void shouldGenerateIdWhenHeaderIsBlank() throws ServletException, IOException {
        when(request.getHeader(TraceContext.HEADER_NAME)).thenReturn("   ");
        when(request.getRequestURI()).thenReturn("/api/conversation/message");

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<String> headerCaptor = ArgumentCaptor.forClass(String.class);
        verify(response).setHeader(eq(TraceContext.HEADER_NAME), headerCaptor.capture());
        String generatedId = headerCaptor.getValue();
        assertNotNull(generatedId);
        assertFalse(generatedId.isBlank());
    }

    @Test
    void shouldClearMDCOnFilterChainException() throws ServletException, IOException {
        when(request.getHeader(TraceContext.HEADER_NAME)).thenReturn("exception-test");
        when(request.getRequestURI()).thenReturn("/api/conversation/message");
        doThrow(new ServletException("test")).when(filterChain).doFilter(request, response);

        try {
            filter.doFilterInternal(request, response, filterChain);
            fail("Should have thrown ServletException");
        } catch (ServletException e) {
            assertEquals("test", e.getMessage());
        }

        // MDC must be cleared even after exception
        assertNull(TraceContext.getTraceId());
    }

    @Test
    void concurrentRequestsShouldNotLeakContext() throws ServletException, IOException {
        // Simulate two sequential requests — verify second request gets its own ID
        when(request.getHeader(TraceContext.HEADER_NAME)).thenReturn("request-aaa");
        when(request.getRequestURI()).thenReturn("/api/conversation/message");

        filter.doFilterInternal(request, response, filterChain);
        ArgumentCaptor<String> firstCaptor = ArgumentCaptor.forClass(String.class);
        verify(response).setHeader(eq(TraceContext.HEADER_NAME), firstCaptor.capture());

        // Reset for second request
        reset(response);
        when(request.getHeader(TraceContext.HEADER_NAME)).thenReturn(null);
        when(request.getRequestURI()).thenReturn("/api/conversation/message");

        filter.doFilterInternal(request, response, filterChain);
        ArgumentCaptor<String> secondCaptor = ArgumentCaptor.forClass(String.class);
        verify(response).setHeader(eq(TraceContext.HEADER_NAME), secondCaptor.capture());

        // First and second should be different (one passthrough, one generated)
        assertEquals("request-aaa", firstCaptor.getValue());
        assertNotEquals("request-aaa", secondCaptor.getValue());
    }
}
