package com.hfusionhub.client;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/**
 * AI Client - Call Python AI Service
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class AiClient {

    private final RestTemplate restTemplate;
    private final WebClient webClient;

    @Value("${ai-service.base-url:http://localhost:8001}")
    private String baseUrl;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    public AiClient(RestTemplate restTemplate, WebClient webClient) {
        this.restTemplate = restTemplate;
        this.webClient = webClient;
    }

    /**
     * Chat with AI agent
     *
     * @param message User message
     * @param conversationId Conversation ID
     * @param knowledgeBaseId Knowledge base ID (optional)
     * @param history Chat history
     * @return AI response
     */
    public ChatResponse chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history
    ) {
        try {
            // Build request
            Map<String, Object> request = new HashMap<>();
            request.put("message", message);
            request.put("conversation_id", conversationId);
            request.put("knowledge_base_id", knowledgeBaseId);
            request.put("history", history != null ? history : List.of());
            request.put("stream", false);

            // Set headers
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            addInternalToken(headers);

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, headers);

            // Call Python AI service
            String url = baseUrl + "/api/chat";
            log.info("Calling AI service: {}", url);

            ResponseEntity<ChatResponse> response = restTemplate.exchange(
                    url,
                    HttpMethod.POST,
                    entity,
                    ChatResponse.class
            );

            if (response.getBody() != null) {
                return response.getBody();
            }

            throw new BusinessException(StatusCode.SERVICE_UNAVAILABLE, "AI service returned empty response");

        } catch (BusinessException e) {
            throw e;
        } catch (ResourceAccessException e) {
            log.error("AI service connection failed: {}", e.getMessage());
            throw new BusinessException(StatusCode.SERVICE_UNAVAILABLE, "AI service is unavailable. Please try again later.");
        } catch (Exception e) {
            log.error("Chat with AI failed: {}", e.getMessage(), e);
            throw new BusinessException(StatusCode.INTERNAL_ERROR, "Failed to get AI response: " + e.getMessage());
        }
    }

    /**
     * Chat with AI agent (true streaming via WebClient).
     *
     * Returns a Flux of SSE data lines from the Python AI service.
     * Each emission is one raw SSE line (including "data: " prefix and "[DONE]" sentinel).
     * The returned Flux supports cancellation via the subscription's dispose().
     *
     * @param message       User message
     * @param conversationId Conversation ID
     * @param knowledgeBaseId Knowledge base ID (optional)
     * @param history        Chat history
     * @param requestId      Unique request ID (for idempotency + cancellation)
     * @return Flux of raw SSE lines
     */
    public reactor.core.publisher.Flux<String> streamChat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String requestId
    ) {
        // Build request body
        Map<String, Object> request = new HashMap<>();
        request.put("message", message);
        request.put("conversation_id", conversationId);
        request.put("knowledge_base_id", knowledgeBaseId);
        request.put("history", history != null ? history : List.of());
        request.put("stream", true);
        request.put("request_id", requestId);

        String url = baseUrl + "/api/chat/stream";
        log.info("Starting streaming request to Python AI: {}, requestId: {}", url, requestId);

        return webClient.post()
                .uri("/api/chat/stream")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .headers(this::addInternalToken)
                .bodyValue(request)
                .retrieve()
                .onStatus(
                        status -> status.isError(),
                        clientResponse -> clientResponse.bodyToMono(String.class)
                                .flatMap(body -> reactor.core.publisher.Mono.error(
                                        new BusinessException(StatusCode.SERVICE_UNAVAILABLE,
                                                "Python AI returned status " + clientResponse.statusCode().value() + ": " + body)))
                )
                .bodyToFlux(String.class)
                .doOnError(ResourceAccessException.class, e -> {
                    log.error("AI service connection failed during streaming: {}", e.getMessage());
                })
                .doOnError(e -> {
                    if (!(e instanceof ResourceAccessException)) {
                        log.error("Stream chat with AI failed: {}", e.getMessage(), e);
                    }
                });
    }

    /**
     * Chat with AI agent (streaming) — legacy synchronous wrapper.
     *
     * @deprecated Use {@link #streamChat(String, Long, Long, List, String)} for true streaming.
     *             This method exists only for backward compatibility and does NOT stream.
     */
    @Deprecated
    public StreamResponse chatStream(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history
    ) {
        // Delegate to the synchronous chat() method for backward compatibility.
        // New code should use streamChat() with Flux for true SSE streaming.
        String requestId = java.util.UUID.randomUUID().toString();
        ChatResponse response = chat(message, conversationId, knowledgeBaseId, history);
        return new StreamResponse(response.getContent(), requestId);
    }

    /**
     * Check AI service health
     *
     * @return true if healthy
     */
    public boolean isHealthy() {
        try {
            String url = baseUrl + "/api/chat/health";
            ResponseEntity<Map> response = restTemplate.exchange(
                    url, HttpMethod.GET, new HttpEntity<>(internalHeaders()), Map.class);

            if (response.getBody() != null) {
                Object status = response.getBody().get("status");
                return "healthy".equals(status);
            }
            return false;
        } catch (Exception e) {
            log.warn("AI service health check failed: {}", e.getMessage());
            return false;
        }
    }

    /**
     * Cancel an ongoing chat request
     *
     * @param requestId Request ID to cancel
     * @return true if cancelled successfully
     */
    public boolean cancelRequest(String requestId) {
        try {
            String url = baseUrl + "/api/chat/cancel?request_id=" + requestId;
            ResponseEntity<Map> response = restTemplate.exchange(
                    url, HttpMethod.POST, new HttpEntity<>(internalHeaders()), Map.class);

            if (response.getBody() != null) {
                Object status = response.getBody().get("status");
                return "cancelled".equals(status);
            }
            return false;
        } catch (Exception e) {
            log.warn("Cancel request failed: {}", e.getMessage());
            return false;
        }
    }

    private HttpHeaders internalHeaders() {
        HttpHeaders headers = new HttpHeaders();
        addInternalToken(headers);
        return headers;
    }

    private void addInternalToken(HttpHeaders headers) {
        if (internalApiToken == null || internalApiToken.isBlank()) {
            throw new BusinessException(StatusCode.INTERNAL_ERROR, "PYTHON_AI_INTERNAL_TOKEN 未配置");
        }
        headers.set("X-Internal-Token", internalApiToken);
    }

    /**
     * Chat response data model
     */
    public static class ChatResponse {
        private String content;
        private String model;
        @JsonProperty("token_count")
        private int tokenCount;
        private List<Map<String, Object>> steps;
        private List<Map<String, Object>> sources;
        @JsonProperty("auto_detected_kb_id")
        private Long autoDetectedKbId;

        public ChatResponse() {}

        public String getContent() { return content; }
        public void setContent(String content) { this.content = content; }

        public String getModel() { return model; }
        public void setModel(String model) { this.model = model; }

        public int getTokenCount() { return tokenCount; }
        public void setTokenCount(int tokenCount) { this.tokenCount = tokenCount; }

        public List<Map<String, Object>> getSteps() { return steps; }
        public void setSteps(List<Map<String, Object>> steps) { this.steps = steps; }

        public List<Map<String, Object>> getSources() { return sources; }
        public void setSources(List<Map<String, Object>> sources) { this.sources = sources; }

        public Long getAutoDetectedKbId() { return autoDetectedKbId; }
        public void setAutoDetectedKbId(Long autoDetectedKbId) { this.autoDetectedKbId = autoDetectedKbId; }
    }

    /**
     * Stream response with request ID for cancellation
     */
    public static class StreamResponse {
        private final String content;
        private final String requestId;

        public StreamResponse(String content, String requestId) {
            this.content = content;
            this.requestId = requestId;
        }

        public String getContent() { return content; }
        public String getRequestId() { return requestId; }
    }
}
