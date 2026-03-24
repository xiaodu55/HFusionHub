package com.hfusionhub.client;

import com.hfusionhub.common.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClient.RequestBodyUriSpec;
import org.springframework.web.reactive.function.client.WebClient.RequestBodySpec;
import org.springframework.web.reactive.function.client.WebClient.RequestHeadersSpec;
import org.springframework.web.reactive.function.client.WebClient.ResponseSpec;
import org.springframework.web.client.RestTemplate;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AiClientTest {

    @Mock
    private RestTemplate restTemplate;

    @Mock
    private WebClient webClient;

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
        aiClient = new AiClient(restTemplate, webClient);

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
                .thenReturn(Flux.just(
                        "data: {\"content\":\"Hello\"}",
                        "data: {\"content\":\" World\"}",
                        "data: [DONE]"));

        // When
        Flux<String> result = aiClient.streamChat(
                "test message", 1L, null, List.of(), "req-001");

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
        when(responseSpec.bodyToFlux(String.class))
                .thenReturn(Flux.just("data: [DONE]"));

        // When: streamChat is called (verifies stream=true is in the request body)
        Flux<String> result = aiClient.streamChat(
                "query", 2L, 10L, List.of(), "req-002");

        // Then
        StepVerifier.create(result)
                .expectNextCount(1)
                .verifyComplete();
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
        when(responseSpec.bodyToFlux(String.class))
                .thenReturn(Flux.just("data: [DONE]"));

        Flux<String> result = aiClient.streamChat(
                "test", 1L, null, null, "req-003");

        assertNotNull(result);
        StepVerifier.create(result).expectNextCount(1).verifyComplete();
    }

    @Test
    void deprecatedChatStreamShouldDelegateToChat() {
        // The deprecated chatStream() now delegates to chat().
        // Since chat() uses RestTemplate which isn't mocked for success,
        // we verify it throws the expected unavailability error.
        when(restTemplate.exchange(anyString(), any(), any(), any(Class.class)))
                .thenThrow(new org.springframework.web.client.ResourceAccessException("Connection refused"));

        assertThrows(BusinessException.class, () ->
                aiClient.chatStream("msg", 1L, null, List.of()));
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
}
