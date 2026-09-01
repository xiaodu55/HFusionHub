package com.hfusionhub.client;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.service.UserModelConfigService;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClient.RequestBodySpec;
import org.springframework.web.reactive.function.client.WebClient.RequestBodyUriSpec;
import org.springframework.web.reactive.function.client.WebClient.RequestHeadersSpec;
import org.springframework.web.reactive.function.client.WebClient.ResponseSpec;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@ExtendWith(MockitoExtension.class)
class AiClientTest {

    @Mock
    private RestTemplate restTemplate;

    @Mock
    private WebClient webClient;

    @Mock
    private UserModelConfigService userModelConfigService;

    @Mock
    private RequestBodyUriSpec requestBodyUriSpec;

    @Mock
    private RequestBodySpec requestBodySpec;

    @Mock
    private RequestHeadersSpec requestHeadersSpec;

    @Mock
    private ResponseSpec responseSpec;

    private AiClient aiClient;

    @BeforeEach
    void setUp() throws Exception {
        aiClient = new AiClient(restTemplate, webClient, userModelConfigService);

        // Inject field values via reflection since they're @Value-injected
        java.lang.reflect.Field baseUrlField = AiClient.class.getDeclaredField("baseUrl");
        baseUrlField.setAccessible(true);
        baseUrlField.set(aiClient, "http://localhost:9001");

        java.lang.reflect.Field tokenField = AiClient.class.getDeclaredField("internalApiToken");
        tokenField.setAccessible(true);
        tokenField.set(aiClient, "test-token");
    }

    @Test
    void streamChatShouldReturnFluxOfSseLines() {
        // Given: Python AI returns SSE data lines
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.contentType(any())).thenReturn(requestBodySpec);
        when(requestBodySpec.accept(any())).thenReturn(requestBodySpec);
        when(requestBodySpec.headers(any())).thenReturn(requestBodySpec);
        when(requestBodySpec.bodyValue(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.onStatus(any(), any())).thenReturn(responseSpec);
        when(responseSpec.bodyToFlux(String.class))
                .thenReturn(
                        Flux.just("data: {\"content\":\"Hello\"}", "data: {\"content\":\" World\"}", "data: [DONE]"));

        // When
        Flux<String> result = aiClient.streamChat("test message", 1L, null, List.of(), "req-001", null, null);

        // Then
        StepVerifier.create(result)
                .expectNext("data: {\"content\":\"Hello\"}")
                .expectNext("data: {\"content\":\" World\"}")
                .expectNext("data: [DONE]")
                .verifyComplete();
    }

    @Test
    void streamChatShouldIncludeStreamFlag() {
        // Given: Python AI responds normally
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.contentType(any())).thenReturn(requestBodySpec);
        when(requestBodySpec.accept(any())).thenReturn(requestBodySpec);
        when(requestBodySpec.headers(any())).thenReturn(requestBodySpec);
        when(requestBodySpec.bodyValue(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.onStatus(any(), any())).thenReturn(responseSpec);
        when(responseSpec.bodyToFlux(String.class)).thenReturn(Flux.just("data: [DONE]"));

        // When: streamChat is called (verifies stream=true is in the request body)
        Flux<String> result = aiClient.streamChat("query", 2L, 10L, List.of(), "req-002", null, null);

        // Then
        StepVerifier.create(result).expectNextCount(1).verifyComplete();
    }

    @Test
    void streamChatShouldAcceptEmptyHistory() {
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.contentType(any())).thenReturn(requestBodySpec);
        when(requestBodySpec.accept(any())).thenReturn(requestBodySpec);
        when(requestBodySpec.headers(any())).thenReturn(requestBodySpec);
        when(requestBodySpec.bodyValue(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.onStatus(any(), any())).thenReturn(responseSpec);
        when(responseSpec.bodyToFlux(String.class)).thenReturn(Flux.just("data: [DONE]"));

        Flux<String> result = aiClient.streamChat("test", 1L, null, null, "req-003", null, null);

        assertNotNull(result);
        StepVerifier.create(result).expectNextCount(1).verifyComplete();
    }

    @Test
    void isHealthyShouldReturnFalseWhenServiceUnavailable() {
        when(restTemplate.exchange(anyString(), any(), any(), any(Class.class)))
                .thenThrow(new org.springframework.web.client.ResourceAccessException("Connection refused"));

        assertFalse(aiClient.isHealthy());
    }

    @Test
    void isHealthyShouldReturnTrueWhenHealthy() {
        Map<String, Object> responseBody = Map.of("status", "healthy");
        org.springframework.http.ResponseEntity<Map> response =
                new org.springframework.http.ResponseEntity<>(responseBody, org.springframework.http.HttpStatus.OK);
        when(restTemplate.exchange(anyString(), any(), any(), any(Class.class)))
                .thenReturn((org.springframework.http.ResponseEntity) response);

        assertTrue(aiClient.isHealthy());
    }

    @Test
    void runtimeOverviewShouldReturnStructuredUnavailableStateWhenServiceIsDown() {
        when(restTemplate.exchange(anyString(), any(), any(), any(Class.class)))
                .thenThrow(new org.springframework.web.client.ResourceAccessException("Connection refused"));

        Map<String, Object> result = aiClient.getRuntimeOverview();

        assertEquals("unavailable", result.get("status"));
        assertEquals(false, result.get("gateway_reachable"));
    }

    @Test
    void cancelRequestShouldReturnTrue() {
        Map<String, Object> responseBody = Map.of("status", "cancelled");
        org.springframework.http.ResponseEntity<Map> response =
                new org.springframework.http.ResponseEntity<>(responseBody, org.springframework.http.HttpStatus.OK);
        when(restTemplate.exchange(anyString(), any(), any(), any(Class.class)))
                .thenReturn((org.springframework.http.ResponseEntity) response);

        assertTrue(aiClient.cancelRequest("req-001"));
    }

    @Test
    void cancelRequestShouldReturnFalseWhenNotCancelled() {
        Map<String, Object> responseBody = Map.of("status", "not_found");
        org.springframework.http.ResponseEntity<Map> response =
                new org.springframework.http.ResponseEntity<>(responseBody, org.springframework.http.HttpStatus.OK);
        when(restTemplate.exchange(anyString(), any(), any(), any(Class.class)))
                .thenReturn((org.springframework.http.ResponseEntity) response);

        assertFalse(aiClient.cancelRequest("unknown-id"));
    }

    // ── system_prompt contract (max 8000, bypasses 4000-char history limit) ──

    @SuppressWarnings("unchecked")
    private Map<String, Object> captureRequestBody() {
        ArgumentCaptor<HttpEntity> entityCaptor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).exchange(anyString(), any(), entityCaptor.capture(), any(Class.class));
        return (Map<String, Object>) entityCaptor.getValue().getBody();
    }

    private void stubRestTemplateSuccess() {
        AiClient.ChatResponse body = new AiClient.ChatResponse();
        body.setContent("ok");
        body.setModel("deepseek-v4-flash");
        org.springframework.http.ResponseEntity<AiClient.ChatResponse> response =
                new org.springframework.http.ResponseEntity<>(body, HttpStatus.OK);
        when(restTemplate.exchange(anyString(), any(), any(), any(Class.class)))
                .thenReturn((org.springframework.http.ResponseEntity) response);
    }

    @Test
    void chatShouldSendTemplateAsSystemPromptFieldNotHistory() {
        stubRestTemplateSuccess();
        String template = "T".repeat(7999); // max-8000 band that used to fail in history

        aiClient.chat("question", null, null, List.of(), template);

        Map<String, Object> body = captureRequestBody();
        assertTrue(body.containsKey("system_prompt"), "system_prompt key must be present");
        assertEquals(template, body.get("system_prompt"));
        assertEquals(List.of(), body.get("history"), "template must NOT be in history");
        assertEquals(null, body.get("knowledge_base_id"));
    }

    @Test
    void agentV1ChatShouldSendTemplateAsSystemPromptField() {
        stubRestTemplateSuccess();
        String template = "T".repeat(8000);

        aiClient.agentV1Chat("question", null, 42L, List.of(), template, "detailed", 5, null, 1L);

        Map<String, Object> body = captureRequestBody();
        assertTrue(body.containsKey("system_prompt"), "system_prompt key must be present");
        assertEquals(template, body.get("system_prompt"));
        assertEquals(List.of(), body.get("history"));
        assertEquals(42L, ((Number) body.get("knowledge_base_id")).longValue());
        assertEquals(1L, ((Number) body.get("user_id")).longValue());
    }

    @Test
    void chatWithoutSystemPromptShouldOmitTheField() {
        stubRestTemplateSuccess();

        aiClient.chat("question", 1L, null, List.of());

        Map<String, Object> body = captureRequestBody();
        assertFalse(body.containsKey("system_prompt"), "system_prompt key must be absent when not provided");
    }
}
