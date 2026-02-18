package com.hfusionhub.client;

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

            throw new BusinessException("AI service returned empty response");

        } catch (ResourceAccessException e) {
            log.error("AI service connection failed: {}", e.getMessage());
            throw new BusinessException("AI service is unavailable. Please try again later.");
        } catch (Exception e) {
            log.error("Chat with AI failed: {}", e.getMessage(), e);
            throw new BusinessException("Failed to get AI response: " + e.getMessage());
        }
    }

    /**
     * Chat with AI agent (streaming)
     *
     * @param message User message
     * @param conversationId Conversation ID
     * @param knowledgeBaseId Knowledge base ID (optional)
     * @param history Chat history
     * @return Streaming response
     */
    public StreamResponse chatStream(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history
    ) {
        try {
            // Generate request ID for cancellation tracking
            String requestId = java.util.UUID.randomUUID().toString();

            // Build request
            Map<String, Object> request = new HashMap<>();
            request.put("message", message);
            request.put("conversation_id", conversationId);
            request.put("knowledge_base_id", knowledgeBaseId);
            request.put("history", history != null ? history : List.of());
            request.put("stream", true);
            request.put("request_id", requestId);

            // Set headers
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.set("Accept", "text/event-stream");
            addInternalToken(headers);

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, headers);

            // Call Python AI service (non-streaming for simplicity)
            // In production, you might want to use WebFlux or similar for true streaming
            String url = baseUrl + "/api/chat";
            log.info("Calling AI service: {}, requestId: {}", url, requestId);

            // Change stream to false for non-streaming response
            request.put("stream", false);
            entity = new HttpEntity<>(request, headers);

            ResponseEntity<ChatResponse> response = restTemplate.exchange(
                    url,
                    HttpMethod.POST,
                    entity,
                    ChatResponse.class
            );

            if (response.getBody() != null) {
                return new StreamResponse(response.getBody().getContent(), requestId);
            }

            throw new BusinessException("AI service returned empty response");

        } catch (ResourceAccessException e) {
            log.error("AI service connection failed: {}", e.getMessage());
            throw new BusinessException("AI service is unavailable. Please try again later.");
        } catch (Exception e) {
            log.error("Chat stream with AI failed: {}", e.getMessage(), e);
            throw new BusinessException("Failed to get AI response: " + e.getMessage());
        }
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
            throw new BusinessException("PYTHON_AI_INTERNAL_TOKEN 未配置");
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
