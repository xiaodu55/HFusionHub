package com.hfusionhub.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.tenant.TenantContext;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

/**
 * Unit tests for {@link EvalHarnessController}'s forwarding headers.
 *
 * <p>These routes are pure proxies to python-ai, so the outbound tenant header is
 * the only thing deciding which tenant's data the evaluation runs against — and the
 * summary callback that python-ai fires back is attributed from that same header.</p>
 */
class EvalHarnessControllerTest {

    private RestTemplate restTemplate;
    private EvalHarnessController controller;

    @BeforeEach
    void setUp() {
        restTemplate = mock(RestTemplate.class);
        controller = new EvalHarnessController(restTemplate, mock(KnowledgeBaseMapper.class));
        ReflectionTestUtils.setField(controller, "aiServiceBaseUrl", "http://ai-service:9000");
        ReflectionTestUtils.setField(controller, "internalApiToken", "test-internal-token");
    }

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    @Test
    void listRunsForwardsTheCurrentTenantContext() {
        TenantContext.setTenantId(7L);
        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(HttpEntity.class), eq(Map.class)))
                .thenReturn(new ResponseEntity<>(Map.of("runs", java.util.List.of()), HttpStatus.OK));

        controller.listRuns();

        HttpEntity<?> sent = captureGet();
        assertEquals("7", sent.getHeaders().getFirst("X-Tenant-Id"));
        assertEquals("test-internal-token", sent.getHeaders().getFirst("X-Internal-Token"));
    }

    @Test
    void scorePostForwardsTheSameTenantAsGetRoutes() {
        TenantContext.setTenantId(3L);
        when(restTemplate.exchange(anyString(), eq(HttpMethod.POST), any(HttpEntity.class), eq(Map.class)))
                .thenReturn(new ResponseEntity<>(Map.of("scores_file", "a_scores.json"), HttpStatus.OK));

        controller.score(Map.of("run_file", "a.jsonl"));

        ArgumentCaptor<HttpEntity> captor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate)
                .exchange(
                        eq("http://ai-service:9000/api/eval-harness/score"),
                        eq(HttpMethod.POST),
                        captor.capture(),
                        eq(Map.class));
        assertEquals("3", captor.getValue().getHeaders().getFirst("X-Tenant-Id"));
    }

    @Test
    void tenantHeaderIsOmittedWhenNoTenantContextResolved() {
        // 不带头 ≠ 带 1：python-ai 的租户守卫据此 400，而不是把评测记到 tenant 1 名下
        when(restTemplate.exchange(anyString(), eq(HttpMethod.GET), any(HttpEntity.class), eq(Map.class)))
                .thenReturn(new ResponseEntity<>(Map.of("runs", java.util.List.of()), HttpStatus.OK));

        controller.listRuns();

        HttpEntity<?> sent = captureGet();
        assertNull(sent.getHeaders().getFirst("X-Tenant-Id"));
    }

    @Test
    void missingInternalTokenFailsBeforeAnyForward() {
        ReflectionTestUtils.setField(controller, "internalApiToken", "");
        TenantContext.setTenantId(7L);

        BusinessException exception = assertThrows(BusinessException.class, controller::listRuns);

        assertEquals(StatusCode.INTERNAL_ERROR, exception.getCode());
        verify(restTemplate, org.mockito.Mockito.never())
                .exchange(anyString(), any(HttpMethod.class), any(HttpEntity.class), eq(Map.class));
    }

    private HttpEntity<?> captureGet() {
        ArgumentCaptor<HttpEntity> captor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).exchange(anyString(), eq(HttpMethod.GET), captor.capture(), eq(Map.class));
        return captor.getValue();
    }
}
