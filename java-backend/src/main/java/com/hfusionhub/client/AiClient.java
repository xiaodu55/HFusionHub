package com.hfusionhub.client;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.service.UserModelConfigService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.util.UriComponentsBuilder;

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
    private final UserModelConfigService userModelConfigService;

    @Value("${ai-service.base-url:http://localhost:9000}")
    private String baseUrl;

    @Value("${python-ai.internal-token:}")
    private String internalApiToken;

    public AiClient(RestTemplate restTemplate, WebClient webClient, UserModelConfigService userModelConfigService) {
        this.restTemplate = restTemplate;
        this.webClient = webClient;
        this.userModelConfigService = userModelConfigService;
    }

    @jakarta.annotation.PostConstruct
    void warnIfTokenMissing() {
        // 启动期大声提示（生产 compose 已 :?required 强制；dev/测试空值合法不阻断）。
        // 此前只在调用时才发现，排障成本高。
        if (internalApiToken == null || internalApiToken.isBlank()) {
            log.error("PYTHON_AI_INTERNAL_TOKEN 未配置 —— 所有 AI 调用将失败。"
                    + "生产由 compose :?required 强制注入；本地联调请在环境变量或 application.yml 配置");
        }
    }

    /**
     * Chat with AI agent — general path (knowledge_base_id optional).
     *
     * <p>不自动重试：/api/chat 是非幂等调用（Python 侧已有完整的 LLM
     * 重试预算与用量结算），Java 侧整体重发会造成 LLM 重复消费与
     * 对话状态重复写入。瞬时连接失败会直接抛给调用方/前端显式重试。
     *
     * @param message User message
     * @param conversationId Conversation ID
     * @param knowledgeBaseId Knowledge base ID (optional)
     * @param history Chat history
     * @return AI response
     */
    public ChatResponse chat(
            String message, Long conversationId, Long knowledgeBaseId, List<Map<String, String>> history) {
        return doChat(
                "/api/chat",
                message,
                conversationId,
                knowledgeBaseId,
                history,
                "detailed",
                5,
                null,
                null,
                null,
                null,
                null,
                null);
    }

    public ChatResponse chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            Long userId,
            List<Map<String, Object>> intentContext) {
        return chat(message, conversationId, knowledgeBaseId, history, userId, intentContext, null);
    }

    /** 对话图片输入变体：images 为 base64 data URL 列表（可为空）。 */
    public ChatResponse chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            Long userId,
            List<Map<String, Object>> intentContext,
            List<String> images) {
        return doChat(
                "/api/chat",
                message,
                conversationId,
                knowledgeBaseId,
                history,
                "detailed",
                5,
                null,
                userId,
                null,
                null,
                null,
                intentContext);
    }

    /**
     * Chat with AI agent — general path with style control.
     *
     * <p>非幂等调用，不自动重试（同上）。</p>
     */
    public ChatResponse chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String style,
            int maxToolSteps) {
        return doChat(
                "/api/chat",
                message,
                conversationId,
                knowledgeBaseId,
                history,
                style,
                maxToolSteps,
                null,
                null,
                null,
                null,
                null,
                null);
    }

    /**
     * Chat with AI agent — general path with system prompt.
     *
     * @param systemPrompt Optional system instruction (max 8000 chars on Python side,
     *                     bypasses the 4000-char ChatMessage limit).  Prepended to history.
     */
    public ChatResponse chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String systemPrompt) {
        return doChat(
                "/api/chat",
                message,
                conversationId,
                knowledgeBaseId,
                history,
                "detailed",
                5,
                null,
                null,
                null,
                systemPrompt,
                null,
                null);
    }

    public ChatResponse chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String systemPrompt,
            Long userId) {
        return doChat(
                "/api/chat",
                message,
                conversationId,
                knowledgeBaseId,
                history,
                "detailed",
                5,
                null,
                userId,
                null,
                systemPrompt,
                null,
                null);
    }

    /**
     * Agent V1 chat — REQUIRES knowledge_base_id and user_id.
     *
     * Calls {@code POST /api/agent/v1/chat}.  Returns 422 if
     * knowledgeBaseId or userId is null (enforced at Python side).
     *
     * @param message         User message
     * @param conversationId  Conversation ID
     * @param knowledgeBaseId Knowledge base ID (REQUIRED, non-null)
     * @param history         Chat history
     * @param style           Answer style (concise | detailed | report)
     * @param maxToolSteps    Max ReAct tool-calling steps (1–10)
     * @param requestId       Idempotency key for SSE dedup
     * @param userId          Authenticated user ID from Java session (REQUIRED, non-null)
     * @return AI response with full V1 fields
     */
    public ChatResponse agentV1Chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String style,
            int maxToolSteps,
            String requestId,
            Long userId) {
        return agentV1Chat(
                message, conversationId, knowledgeBaseId, history, style, maxToolSteps, requestId, userId, null, null);
    }

    /**
     * Agent V1 chat with optional {@code capabilityProfile}.
     *
     * {@code capabilityProfile = "approval_write"} enables the V1.1 write-
     * capability tool set (write_note); the agent can SEE the tool but the
     * registry returns approval_required on invocation.  Must be explicitly
     * set by Java — the model cannot upgrade its own capability.
     */
    public ChatResponse agentV1Chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String style,
            int maxToolSteps,
            String requestId,
            Long userId,
            String capabilityProfile,
            String userRole) {
        return agentV1Chat(
                message,
                conversationId,
                knowledgeBaseId,
                history,
                style,
                maxToolSteps,
                requestId,
                userId,
                capabilityProfile,
                userRole,
                null);
    }

    public ChatResponse agentV1Chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String style,
            int maxToolSteps,
            String requestId,
            Long userId,
            String capabilityProfile,
            String userRole,
            List<Map<String, Object>> intentContext) {
        return agentV1Chat(
                message, conversationId, knowledgeBaseId, history, style, maxToolSteps,
                requestId, userId, capabilityProfile, userRole, intentContext, null);
    }

    /** 对话图片输入变体：images 为 base64 data URL 列表（可为空）。 */
    public ChatResponse agentV1Chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String style,
            int maxToolSteps,
            String requestId,
            Long userId,
            String capabilityProfile,
            String userRole,
            List<Map<String, Object>> intentContext,
            List<String> images) {
        if (knowledgeBaseId == null || knowledgeBaseId <= 0) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "Agent V1 requires a non-null knowledge_base_id");
        }
        if (userId == null || userId <= 0) {
            throw new BusinessException(
                    StatusCode.BAD_REQUEST,
                    "Agent V1 requires a non-null user_id — Java session must provide authenticated user ID");
        }
        return doChat(
                "/api/agent/v1/chat",
                message,
                conversationId,
                knowledgeBaseId,
                history,
                style,
                maxToolSteps,
                requestId,
                userId,
                capabilityProfile,
                null,
                userRole,
                intentContext);
    }

    /**
     * Agent V1 chat with system prompt — for test bench and similar tooling.
     *
     * @param systemPrompt Optional system instruction (max 8000 chars on Python side,
     *                     placed before history entries).
     */
    public ChatResponse agentV1Chat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String systemPrompt,
            String style,
            int maxToolSteps,
            String requestId,
            Long userId) {
        if (knowledgeBaseId == null || knowledgeBaseId <= 0) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "Agent V1 requires a non-null knowledge_base_id");
        }
        if (userId == null || userId <= 0) {
            throw new BusinessException(
                    StatusCode.BAD_REQUEST,
                    "Agent V1 requires a non-null user_id — Java session must provide authenticated user ID");
        }
        return doChat(
                "/api/agent/v1/chat",
                message,
                conversationId,
                knowledgeBaseId,
                history,
                style,
                maxToolSteps,
                requestId,
                userId,
                null,
                systemPrompt,
                null,
                null);
    }

    private ChatResponse doChat(
            String path,
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String style,
            int maxToolSteps,
            String requestId,
            Long userId,
            String capabilityProfile,
            String systemPrompt,
            String userRole,
            List<Map<String, Object>> intentContext) {
        return doChatInternal(
                path, message, conversationId, knowledgeBaseId, history, style, maxToolSteps,
                requestId, userId, capabilityProfile, systemPrompt, userRole, intentContext, null);
    }

    /** 对话图片输入：images 为 base64 data URL 列表（由 ConversationServiceImpl 从本地文件读取）。 */
    private ChatResponse doChatInternal(
            String path,
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String style,
            int maxToolSteps,
            String requestId,
            Long userId,
            String capabilityProfile,
            String systemPrompt,
            String userRole,
            List<Map<String, Object>> intentContext,
            List<String> images) {
        try {
            Map<String, Object> request = new HashMap<>();
            request.put("message", message);
            request.put("conversation_id", conversationId);
            request.put("knowledge_base_id", knowledgeBaseId);
            request.put("history", history != null ? history : List.of());
            if (images != null && !images.isEmpty()) {
                request.put("images", images);
            }
            request.put("stream", false);
            request.put("style", style != null ? style : "detailed");
            request.put("max_tool_steps", Math.max(1, Math.min(maxToolSteps, 10)));
            if (requestId != null) {
                request.put("request_id", requestId);
            }
            // Agent V1 Step 3: user_id from authenticated Java session.
            // The model CANNOT forge this — the Registry strips any
            // model-supplied user_id from tool input.
            if (userId != null && userId > 0) {
                request.put("user_id", userId);
            }
            // Agent V1 Step 5: capability_profile explicitly chosen by Java.
            // "approval_write" enables V1.1 write tools (write_note) with
            // approval_required gating.  The model cannot set this itself.
            if (capabilityProfile != null && !capabilityProfile.isEmpty()) {
                request.put("capability_profile", capabilityProfile);
            }
            // Agent governance: authenticatec role (user|admin) so Python's policy
            // engine can apply role-based rules (e.g. admin bypass for approvals).
            if (userRole != null && !userRole.isEmpty()) {
                request.put("user_role", userRole);
            }
            if (systemPrompt != null && !systemPrompt.isEmpty()) {
                request.put("system_prompt", systemPrompt);
            }
            if (intentContext != null && !intentContext.isEmpty()) {
                request.put("intent_context", intentContext);
            }
            addUserProviderConfig(request, userId);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            addInternalToken(headers);
            // 主体级 ACL（V85）：clearance 与租户同边界传播。user_role 由调用方
            // 从认证会话/DB 解析（后台队列无 JWT 时取库内角色）；admin → admin
            // （全 clearance），其余 → general（fail-closed 最小权限）。
            headers.set("X-User-Clearance", mapClearance(userRole));

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, headers);

            String url = baseUrl + path;
            log.info("Calling AI service: {}", url);

            ResponseEntity<ChatResponse> response =
                    restTemplate.exchange(url, HttpMethod.POST, entity, ChatResponse.class);

            if (response.getBody() != null) {
                return response.getBody();
            }

            throw new BusinessException(StatusCode.SERVICE_UNAVAILABLE, "AI service returned empty response");

        } catch (BusinessException e) {
            throw e;
        } catch (ResourceAccessException e) {
            log.error("AI service connection failed: {}", e.getMessage());
            throw new BusinessException(
                    StatusCode.SERVICE_UNAVAILABLE, "AI service is unavailable. Please try again later.");
        } catch (Exception e) {
            log.error("Chat with AI failed: {}", e.getMessage(), e);
            throw new BusinessException(
                    StatusCode.INTERNAL_ERROR, "Failed to get AI response. Please try again later.");
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
            String requestId,
            Long userId,
            List<Map<String, Object>> intentContext) {
        return streamChat(message, conversationId, knowledgeBaseId, history, requestId, userId, intentContext, null);
    }

    /** 对话图片输入变体：images 为 base64 data URL 列表（可为空）。 */
    public reactor.core.publisher.Flux<String> streamChat(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String requestId,
            Long userId,
            List<Map<String, Object>> intentContext,
            List<String> images) {
        // Build request body
        Map<String, Object> request = new HashMap<>();
        request.put("message", message);
        request.put("conversation_id", conversationId);
        request.put("knowledge_base_id", knowledgeBaseId);
        request.put("history", history != null ? history : List.of());
        request.put("stream", true);
        request.put("request_id", requestId);
        if (userId != null && userId > 0) {
            request.put("user_id", userId);
        }
        if (intentContext != null && !intentContext.isEmpty()) {
            request.put("intent_context", intentContext);
        }
        if (images != null && !images.isEmpty()) {
            request.put("images", images);
        }
        addUserProviderConfig(request, userId);

        String url = baseUrl + "/api/chat/stream";
        log.info("Starting streaming request to Python AI: {}, requestId: {}", url, requestId);

        // Capture headers at call time — TenantContext is ThreadLocal-based
        // and may be null when the WebClient request executes on a Netty
        // event-loop thread during reactive subscription.
        final HttpHeaders capturedHeaders = internalHeaders();

        return webClient
                .post()
                .uri(url)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .headers(h -> h.addAll(capturedHeaders))
                .bodyValue(request)
                .retrieve()
                .onStatus(status -> status.isError(), clientResponse -> clientResponse
                        .bodyToMono(String.class)
                        .flatMap(body -> {
                            log.warn("Python AI error status={} body={}", clientResponse.statusCode().value(),
                                    body.length() > 500 ? body.substring(0, 500) : body);
                            return reactor.core.publisher.Mono.error(new BusinessException(
                                    StatusCode.SERVICE_UNAVAILABLE,
                                    "AI 服务暂时不可用（HTTP " + clientResponse.statusCode().value() + "），请稍后重试"));
                        }))
                .bodyToFlux(String.class)
                .doOnNext(chunk -> log.debug("SSE raw chunk ({}B)", chunk.length()))
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
     * Agent V1 streaming chat — REQUIRES knowledge_base_id and user_id.
     *
     * Calls {@code POST /api/agent/v1/chat/stream}.  Returns a Flux of raw
     * SSE data lines.  KB-bound conversations MUST use this endpoint,
     * NOT {@code /api/chat/stream}, so that the execution context is created
     * and the permission boundary is enforced.
     *
     * @param message         User message
     * @param conversationId  Conversation ID
     * @param knowledgeBaseId Knowledge base ID (REQUIRED, non-null)
     * @param history         Chat history
     * @param requestId       Unique request ID (for idempotency + cancellation)
     * @param userId          Authenticated user ID from Java session (REQUIRED, non-null)
     * @return Flux of raw SSE lines
     */
    public reactor.core.publisher.Flux<String> agentV1ChatStream(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String requestId,
            Long userId) {
        return agentV1ChatStream(message, conversationId, knowledgeBaseId, history, requestId, userId, null);
    }

    /**
     * Agent V1 streaming chat with optional {@code capabilityProfile}.
     *
     * {@code capabilityProfile = "approval_write"} enables the V1.1 write-
     * capability tool set (write_note); the agent can SEE the tool but the
     * registry returns approval_required on invocation.  Must be explicitly
     * set by Java — the model cannot upgrade its own capability.
     */
    public reactor.core.publisher.Flux<String> agentV1ChatStream(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String requestId,
            Long userId,
            String capabilityProfile) {
        return agentV1ChatStream(
                message, conversationId, knowledgeBaseId, history, requestId, userId, capabilityProfile, null);
    }

    public reactor.core.publisher.Flux<String> agentV1ChatStream(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String requestId,
            Long userId,
            String capabilityProfile,
            List<Map<String, Object>> intentContext) {
        return agentV1ChatStream(
                message, conversationId, knowledgeBaseId, history, requestId, userId,
                capabilityProfile, intentContext, null, null);
    }

    /** 对话图片输入变体：images 为 base64 data URL 列表（可为空）。
     *
     * @param userRole 认证主体角色（admin|user）：映射 X-User-Clearance 传播
     *                 主体 clearance（admin 全可见，user/general 仅一般文档）。
     *                 后台队列等无 JWT 上下文的调用方须从库内角色解析。
     */
    public reactor.core.publisher.Flux<String> agentV1ChatStream(
            String message,
            Long conversationId,
            Long knowledgeBaseId,
            List<Map<String, String>> history,
            String requestId,
            Long userId,
            String capabilityProfile,
            List<Map<String, Object>> intentContext,
            List<String> images,
            String userRole) {
        if (knowledgeBaseId == null || knowledgeBaseId <= 0) {
            throw new BusinessException(
                    StatusCode.BAD_REQUEST, "Agent V1 streaming requires a non-null knowledge_base_id");
        }
        if (userId == null || userId <= 0) {
            throw new BusinessException(
                    StatusCode.BAD_REQUEST,
                    "Agent V1 streaming requires a non-null user_id — Java session must provide authenticated user ID");
        }

        // Build request body with execution context fields.
        Map<String, Object> request = new HashMap<>();
        request.put("message", message);
        request.put("conversation_id", conversationId);
        request.put("knowledge_base_id", knowledgeBaseId);
        request.put("user_id", userId);
        request.put("history", history != null ? history : List.of());
        request.put("stream", true);
        request.put("request_id", requestId);
        // Agent V1 Step 5: capability_profile explicitly chosen by Java.
        if (capabilityProfile != null && !capabilityProfile.isEmpty()) {
            request.put("capability_profile", capabilityProfile);
        }
        if (intentContext != null && !intentContext.isEmpty()) {
            request.put("intent_context", intentContext);
        }
        if (images != null && !images.isEmpty()) {
            request.put("images", images);
        }
        addUserProviderConfig(request, userId);

        String url = baseUrl + "/api/agent/v1/chat/stream";
        log.info(
                "Starting Agent V1 streaming request to Python AI: {}, requestId: {}, userId: {}",
                url,
                requestId,
                userId);

        // Capture headers at call time — TenantContext is ThreadLocal-based
        // and may be null when the WebClient request executes on a Netty
        // event-loop thread during reactive subscription.
        final HttpHeaders capturedV1Headers = internalHeaders();
        // 主体级 ACL（V85）：与 doChat 同规则，clearance 随流式请求传播
        capturedV1Headers.set("X-User-Clearance", mapClearance(userRole));

        return webClient
                .post()
                .uri(url)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .headers(h -> h.addAll(capturedV1Headers))
                .bodyValue(request)
                .retrieve()
                .onStatus(status -> status.isError(), clientResponse -> clientResponse
                        .bodyToMono(String.class)
                        .flatMap(body -> {
                            log.warn("Python AI error status={} body={}", clientResponse.statusCode().value(),
                                    body.length() > 500 ? body.substring(0, 500) : body);
                            return reactor.core.publisher.Mono.error(new BusinessException(
                                    StatusCode.SERVICE_UNAVAILABLE,
                                    "AI 服务暂时不可用（HTTP " + clientResponse.statusCode().value() + "），请稍后重试"));
                        }))
                .bodyToFlux(String.class)
                .doOnNext(chunk -> log.debug("Agent V1 SSE raw chunk ({}B)", chunk.length()))
                .doOnError(ResourceAccessException.class, e -> {
                    log.error("AI service connection failed during V1 streaming: {}", e.getMessage());
                })
                .doOnError(e -> {
                    if (!(e instanceof ResourceAccessException)) {
                        log.error("Agent V1 stream chat failed: {}", e.getMessage(), e);
                    }
                });
    }

    /**
     * Check AI service health
     *
     * @return true if healthy
     */
    public boolean isHealthy() {
        try {
            String url = baseUrl + "/api/chat/health";
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.GET, new HttpEntity<>(internalHeaders()), Map.class);

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
     * Get the tool registry metadata from the Python AI service.
     *
     * <p>Calls {@code GET /api/tools/registry} on the Python side and returns
     * the full tool list with name, description, risk level, permissions,
     * timeout, and version-gating status.  Safe to call without a knowledge
     * base — only metadata, no execution.</p>
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getToolRegistry(Long tenantId) {
        try {
            String url = UriComponentsBuilder.fromHttpUrl(baseUrl + "/api/tools/registry")
                    .queryParam("tenant_id", tenantId)
                    .toUriString();
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.GET, new HttpEntity<>(internalHeaders()), Map.class);
            if (response.getBody() == null) {
                return Map.of("tools", List.of(), "total", 0, "error", "AI 服务返回了空的工具注册表。");
            }
            return new HashMap<>(response.getBody());
        } catch (Exception e) {
            log.warn("Tool registry unavailable: {}", e.getMessage());
            return Map.of("tools", List.of(), "total", 0, "error", "暂时无法连接 AI 服务获取工具列表。");
        }
    }

    /**
     * Get a safe snapshot of the AI runtime from the internal Python service.
     *
     * <p>Diagnostics must still be usable while the AI service is down, so a
     * structured unavailable response is returned instead of propagating a
     * gateway exception to the UI.</p>
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getRuntimeOverview() {
        try {
            String url = baseUrl + "/api/runtime/overview";
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.GET, new HttpEntity<>(internalHeaders()), Map.class);
            if (response.getBody() == null) {
                return Map.of(
                        "status", "unavailable",
                        "gateway_reachable", false,
                        "detail", "AI 服务返回了空的运行状态。");
            }

            Map<String, Object> overview = new HashMap<>(response.getBody());
            overview.put("gateway_reachable", true);
            return overview;
        } catch (Exception e) {
            log.warn("AI runtime overview unavailable: {}", e.getMessage());
            return Map.of(
                    "status", "unavailable",
                    "gateway_reachable", false,
                    "detail", "暂时无法连接 AI 服务，请确认 AI 服务已启动后重试。");
        }
    }

    @SuppressWarnings("unchecked")
    @Retryable(
            retryFor = {ResourceAccessException.class, HttpServerErrorException.class},
            maxAttempts = 3,
            backoff = @Backoff(delay = 1000, multiplier = 2, maxDelay = 10000))
    public Map<String, Object> testUserProvider(Map<String, Object> providerConfig) {
        try {
            String url = baseUrl + "/api/runtime/provider/test";
            Map<String, Object> request = Map.of("provider_config", providerConfig);
            HttpHeaders headers = internalHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.POST, new HttpEntity<>(request, headers), Map.class);
            if (response.getBody() == null) {
                return Map.of("success", false, "message", "AI 服务没有返回测试结果");
            }
            return new HashMap<>(response.getBody());
        } catch (Exception e) {
            log.warn("User model provider test failed: {}", e.getMessage());
            return Map.of("success", false, "message", "连接失败，请检查 Base URL、模型名称和 API Key");
        }
    }

    /**
     * Ask the Python AI service to fetch a public HTTPS webpage and stage it
     * as a markdown file inside the shared document storage root.
     *
     * @param url   the public HTTPS URL to ingest
     * @param title optional title override
     * @return map with success, file_path, file_type, title, content_length, message
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> ingestUrl(String url, String title) {
        try {
            String requestUrl = baseUrl + "/api/ingest/url";
            Map<String, Object> body = new HashMap<>();
            body.put("url", url);
            if (title != null && !title.isBlank()) {
                body.put("title", title);
            }
            HttpHeaders headers = internalHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            ResponseEntity<Map> response =
                    restTemplate.exchange(requestUrl, HttpMethod.POST, new HttpEntity<>(body, headers), Map.class);
            if (response.getBody() == null) {
                return Map.of("success", false, "message", "AI 服务没有返回抓取结果");
            }
            return new HashMap<>(response.getBody());
        } catch (Exception e) {
            log.warn("URL ingestion failed: {}", e.getMessage());
            return Map.of("success", false, "message", "网页抓取失败，请确认 AI 服务可用且地址为公开 HTTPS 网页");
        }
    }

    // ── MCP client admin (B5) ──────────────────────────────────────────

    @SuppressWarnings("unchecked")
    public Map<String, Object> listMcpServers() {
        try {
            String url = baseUrl + "/api/mcp/servers";
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.GET, new HttpEntity<>(internalHeaders()), Map.class);
            return response.getBody() == null ? Map.of("servers", List.of()) : new HashMap<>(response.getBody());
        } catch (Exception e) {
            log.warn("MCP server list unavailable: {}", e.getMessage());
            return Map.of("servers", List.of(), "error", "暂时无法连接 AI 服务获取 MCP 服务器列表。");
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> addMcpServer(Map<String, Object> body) {
        try {
            String url = baseUrl + "/api/mcp/servers";
            HttpHeaders headers = internalHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.POST, new HttpEntity<>(body, headers), Map.class);
            return response.getBody() == null
                    ? Map.of("success", false, "message", "AI 服务没有返回结果")
                    : new HashMap<>(response.getBody());
        } catch (Exception e) {
            log.warn("MCP server add failed: {}", e.getMessage());
            return Map.of("success", false, "message", "连接 AI 服务失败，请稍后重试");
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> reconnectMcpServer(String serverId) {
        try {
            String url = baseUrl + "/api/mcp/servers/" + serverId + "/reconnect";
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.POST, new HttpEntity<>(internalHeaders()), Map.class);
            return response.getBody() == null
                    ? Map.of("success", false, "message", "AI 服务没有返回结果")
                    : new HashMap<>(response.getBody());
        } catch (Exception e) {
            log.warn("MCP server reconnect failed: {}", e.getMessage());
            return Map.of("success", false, "message", "连接 AI 服务失败，请稍后重试");
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> removeMcpServer(String serverId) {
        try {
            String url = baseUrl + "/api/mcp/servers/" + serverId;
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.DELETE, new HttpEntity<>(internalHeaders()), Map.class);
            return response.getBody() == null
                    ? Map.of("success", true, "message", "已移除")
                    : new HashMap<>(response.getBody());
        } catch (Exception e) {
            log.warn("MCP server remove failed: {}", e.getMessage());
            return Map.of("success", false, "message", "连接 AI 服务失败，请稍后重试");
        }
    }

    /**
     * 在线答案评测（C3）— LLM-as-judge 对回答打分，无需标准答案。
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> judgeAnswer(String query, String answer, String context, String model) {
        try {
            String url = baseUrl + "/api/rag/evaluate/answer-judge";
            Map<String, Object> body = new HashMap<>();
            body.put("query", query);
            body.put("answer", answer);
            body.put("context", context == null ? "" : context);
            if (model != null && !model.isBlank()) {
                body.put("model", model);
            }
            HttpHeaders headers = internalHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.POST, new HttpEntity<>(body, headers), Map.class);
            return response.getBody() == null
                    ? Map.of("status", "error", "message", "AI 服务没有返回评测结果")
                    : new HashMap<>(response.getBody());
        } catch (Exception e) {
            log.warn("Answer judge failed: {}", e.getMessage());
            return Map.of("status", "error", "message", "评测服务不可用，请稍后重试");
        }
    }

    /**
     * Notify Python AI of an approval decision — Agent V1 Step 5.
     *
     * Called by AgentTaskServiceImpl after updating MySQL agent_approval.
     * Python registers a scoped grant and re-runs the agent to execute the
     * approved tool (or returns denied status).
     *
     * @param approvalId      UUID of the approval record
     * @param decision        "approved" or "denied"
     * @param reason          optional reason text
     * @param userId          authenticated user who made the decision
     * @param knowledgeBaseId target knowledge base
     * @param toolName        name of the tool to execute (or reject)
     * @param toolInput       original tool parameters (JSON string)
     * @param query           original user query (to re-run agent)
     * @param history         chat history
     * @param conversationId  conversation ID
     * @param model           optional model override
     * @return ChatResponse with the result of the resumed agent run
     */
    public ChatResponse decideApproval(
            String approvalId,
            String decision,
            String reason,
            Long userId,
            Long knowledgeBaseId,
            String toolName,
            String toolInput,
            String toolInputHash,
            String query,
            List<Map<String, String>> history,
            Long conversationId,
            String model,
            String executionToken,
            String userRole) {
        try {
            Map<String, Object> request = new HashMap<>();
            request.put("approval_id", approvalId);
            request.put("decision", decision);
            if (reason != null) request.put("reason", reason);
            request.put("user_id", userId);
            request.put("knowledge_base_id", knowledgeBaseId);
            request.put("tool_name", toolName);
            // Parse tool_input from JSON string to object
            try {
                com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                request.put("tool_input", mapper.readTree(toolInput));
            } catch (Exception e) {
                request.put("tool_input", Map.of("_raw", toolInput));
            }
            request.put("expected_tool_input_hash", toolInputHash);
            request.put("query", query);
            request.put("history", history != null ? history : List.of());
            if (conversationId != null) request.put("conversation_id", conversationId);
            if (model != null) request.put("model", model);
            // Durable one-time execution token (MySQL-backed).  Python MUST
            // consume it via the Java internal endpoint before running the tool;
            // a replayed approve/resume is rejected without side effects.
            if (executionToken != null) request.put("execution_token", executionToken);
            if (userRole != null) request.put("user_role", userRole);
            addUserProviderConfig(request, userId);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            addInternalToken(headers);

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, headers);

            String url = baseUrl + "/api/agent/v1/chat/decide";
            log.info("Calling AI decide endpoint: {} approvalId={} decision={}", url, approvalId, decision);

            ResponseEntity<ChatResponse> response =
                    restTemplate.exchange(url, HttpMethod.POST, entity, ChatResponse.class);

            if (response.getBody() != null) {
                return response.getBody();
            }
            throw new BusinessException(
                    StatusCode.SERVICE_UNAVAILABLE, "AI service returned empty response for decide");

        } catch (BusinessException e) {
            throw e;
        } catch (ResourceAccessException e) {
            log.error("AI decide connection failed: {}", e.getMessage());
            throw new BusinessException(
                    StatusCode.SERVICE_UNAVAILABLE, "AI service is unavailable. Please try again later.");
        } catch (Exception e) {
            log.error("Decide approval failed: {}", e.getMessage(), e);
            throw new BusinessException(
                    StatusCode.INTERNAL_ERROR, "Failed to process approval decision. Please try again later.");
        }
    }

    /**
     * 招投标解读（B2）— 调用 Python 解读工作流，抽取招标文件结构化要素。
     *
     * <p>请求 POST /api/bid/interpret，返回结构化 JSON：
     * {@code {status, elements:[{element_key, element_value, confidence, source_clause, evidence_chunk_ids}],
     * scoring_methods:[{method_type, total_score, points_json}],
     * requirements:[{category, requirement, source_clause, confidence}]}}。
     * 与 judgeAnswer 一致：AI 服务不可用时返回降级 map，不抛网关异常。</p>
     *
     * @param projectId       投标项目 ID
     * @param knowledgeBaseId 招标文件知识库 ID
     * @param title           项目名称
     * @param tenderNumber    招标编号（可空）
     * @return 解读结果 map（含 status）
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> bidInterpret(
            Long projectId, Long knowledgeBaseId, String title, String tenderNumber) {
        try {
            String url = baseUrl + "/api/bid/interpret";
            Map<String, Object> body = new HashMap<>();
            body.put("project_id", projectId);
            body.put("knowledge_base_id", knowledgeBaseId);
            body.put("title", title);
            if (tenderNumber != null && !tenderNumber.isBlank()) {
                body.put("tender_number", tenderNumber);
            }
            HttpHeaders headers = internalHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.POST, new HttpEntity<>(body, headers), Map.class);
            return response.getBody() == null
                    ? Map.of("status", "error", "message", "AI 服务没有返回解读结果")
                    : new HashMap<>(response.getBody());
        } catch (BusinessException e) {
            throw e;
        } catch (Exception e) {
            log.warn("Bid interpret failed: {}", e.getMessage());
            return Map.of("status", "error", "message", "解读服务不可用，请稍后重试");
        }
    }

    /**
     * 标书撰写（P1）— 调用 Python 撰写工作流，按分节生成标书草稿。
     *
     * <p>请求 POST /api/bid/write，返回：
     * {@code {status, sections:[{section_key, section_title, content, evidence_chunk_ids}]}}。
     * 与 bidInterpret 一致：AI 服务不可用时返回降级 map，不抛网关异常。</p>
     *
     * @param projectId         投标项目 ID
     * @param title             项目名称
     * @param tenderNumber      招标编号（可空）
     * @param knowledgeBaseIds  招标库(+资质库/历史标书库) ID 列表
     * @param requirements      已确认需求清单 [{category, requirement, source_clause}]
     * @param sectionDefs       分节定义 [{key, title}]（可空=默认四节）
     * @return 撰写结果 map（含 status）
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> bidWrite(
            Long projectId,
            String title,
            String tenderNumber,
            List<Long> knowledgeBaseIds,
            List<Map<String, Object>> requirements,
            List<Map<String, Object>> sectionDefs) {
        try {
            String url = baseUrl + "/api/bid/write";
            Map<String, Object> body = new HashMap<>();
            body.put("project_id", projectId);
            body.put("title", title);
            if (tenderNumber != null && !tenderNumber.isBlank()) {
                body.put("tender_number", tenderNumber);
            }
            body.put("knowledge_base_ids", knowledgeBaseIds == null ? List.of() : knowledgeBaseIds);
            body.put("requirements", requirements == null ? List.of() : requirements);
            if (sectionDefs != null && !sectionDefs.isEmpty()) {
                body.put("section_defs", sectionDefs);
            }
            HttpHeaders headers = internalHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.POST, new HttpEntity<>(body, headers), Map.class);
            return response.getBody() == null
                    ? Map.of("status", "error", "message", "AI 服务没有返回撰写结果")
                    : new HashMap<>(response.getBody());
        } catch (BusinessException e) {
            throw e;
        } catch (Exception e) {
            log.warn("Bid write failed: {}", e.getMessage());
            return Map.of("status", "error", "message", "撰写服务不可用，请稍后重试");
        }
    }

    /**
     * 废标风险自检（P1）— 调用 Python 自检工作流，核对标书草稿。
     *
     * <p>请求 POST /api/bid/check，返回：
     * {@code {status, findings:[{severity, category, section_key, finding, evidence_chunk_ids, suggested_fix}], summary}}。</p>
     *
     * @param projectId        投标项目 ID
     * @param title            项目名称
     * @param tenderNumber     招标编号（可空）
     * @param knowledgeBaseIds 招标文件知识库 ID 列表
     * @param sections         待自检标书分节 [{section_key, section_title, content}]
     * @param requirements     需求清单（可空）
     * @return 自检结果 map（含 status）
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> bidCheck(
            Long projectId,
            String title,
            String tenderNumber,
            List<Long> knowledgeBaseIds,
            List<Map<String, Object>> sections,
            List<Map<String, Object>> requirements) {
        try {
            String url = baseUrl + "/api/bid/check";
            Map<String, Object> body = new HashMap<>();
            body.put("project_id", projectId);
            body.put("title", title);
            if (tenderNumber != null && !tenderNumber.isBlank()) {
                body.put("tender_number", tenderNumber);
            }
            body.put("knowledge_base_ids", knowledgeBaseIds == null ? List.of() : knowledgeBaseIds);
            body.put("sections", sections == null ? List.of() : sections);
            if (requirements != null && !requirements.isEmpty()) {
                body.put("requirements", requirements);
            }
            HttpHeaders headers = internalHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.POST, new HttpEntity<>(body, headers), Map.class);
            return response.getBody() == null
                    ? Map.of("status", "error", "message", "AI 服务没有返回自检结果")
                    : new HashMap<>(response.getBody());
        } catch (BusinessException e) {
            throw e;
        } catch (Exception e) {
            log.warn("Bid check failed: {}", e.getMessage());
            return Map.of("status", "error", "message", "自检服务不可用，请稍后重试");
        }
    }

    /**
     * 标书撰写（流式，P1）— 调用 Python SSE 撰写工作流。
     *
     * <p>请求 POST /api/bid/write/stream，返回 Flux of raw SSE data lines。
     * 事件契约（与 Python 侧一致）：
     * {@code run_started → (bid_section_started / bid_section_completed)×N → run_completed → [DONE]}。
     * 服务层订阅后转发到 SseEmitter，并在 run_completed 时统一落库。</p>
     *
     * @return Flux of raw SSE lines
     */
    public reactor.core.publisher.Flux<String> bidWriteStream(
            Long projectId,
            String title,
            String tenderNumber,
            List<Long> knowledgeBaseIds,
            List<Map<String, Object>> requirements,
            List<Map<String, Object>> sectionDefs) {
        String url = baseUrl + "/api/bid/write/stream";
        Map<String, Object> request = new HashMap<>();
        request.put("project_id", projectId);
        request.put("title", title);
        if (tenderNumber != null && !tenderNumber.isBlank()) {
            request.put("tender_number", tenderNumber);
        }
        request.put("knowledge_base_ids", knowledgeBaseIds == null ? List.of() : knowledgeBaseIds);
        request.put("requirements", requirements == null ? List.of() : requirements);
        if (sectionDefs != null && !sectionDefs.isEmpty()) {
            request.put("section_defs", sectionDefs);
        }
        // 捕获内部鉴权头，避免在 Netty 事件循环线程上访问请求线程上下文
        final HttpHeaders capturedHeaders = internalHeaders();
        return webClient.post()
                .uri(url)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .headers(h -> h.addAll(capturedHeaders))
                .bodyValue(request)
                .retrieve()
                .onStatus(status -> status.isError(), clientResponse -> clientResponse
                        .bodyToMono(String.class)
                        .flatMap(body -> {
                            log.warn("Python AI error status={} body={}", clientResponse.statusCode().value(),
                                    body.length() > 500 ? body.substring(0, 500) : body);
                            return reactor.core.publisher.Mono.error(new BusinessException(
                                    StatusCode.SERVICE_UNAVAILABLE,
                                    "AI 服务暂时不可用（HTTP " + clientResponse.statusCode().value() + "），请稍后重试"));
                        }))
                .bodyToFlux(String.class)
                .doOnError(ResourceAccessException.class, e -> {
                    log.error("AI service connection failed during bid write streaming: {}", e.getMessage());
                });
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
            ResponseEntity<Map> response =
                    restTemplate.exchange(url, HttpMethod.POST, new HttpEntity<>(internalHeaders()), Map.class);

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

    /**
     * 会话删除前的长期记忆固化（fire-and-forget）。
     *
     * <p>Java 把被删会话的消息快照交给 Python 跑 LLM 记忆抽取（特征开关
     * memory.long_term.enabled 由调用方判定）；Python 抽取完成后经
     * {@code POST /api/internal/memory/entries} 回写 memory_entry 表。
     * 失败只记日志，不影响删除主流程。</p>
     */
    @Async("housekeepingExecutor")
    public void consolidateMemoryOnConversationDeleted(
            Long conversationId, Long userId, Long knowledgeBaseId, Long tenantId,
            List<Map<String, String>> messages) {
        if (internalApiToken == null || internalApiToken.isBlank()
                || messages == null || messages.isEmpty()) {
            return;
        }
        try {
            Map<String, Object> body = new HashMap<>();
            body.put("conversation_id", conversationId);
            body.put("user_id", userId);
            if (knowledgeBaseId != null) body.put("knowledge_base_id", knowledgeBaseId);
            if (tenantId != null) body.put("tenant_id", tenantId);
            body.put("messages", messages);
            restTemplate.postForEntity(
                    baseUrl + "/api/internal/memory/consolidate",
                    new HttpEntity<>(body, internalHeaders()),
                    String.class);
            log.info("Memory consolidation dispatched for deleted conversation {}", conversationId);
        } catch (Exception e) {
            log.warn("Memory consolidation call failed for conversation {}: {}",
                    conversationId, e.getMessage());
        }
    }

    private void addUserProviderConfig(Map<String, Object> request, Long userId) {
        if (userId == null || userId <= 0) return;
        Map<String, Object> providerConfig = userModelConfigService.getRuntimeConfig(userId);
        if (!providerConfig.isEmpty()) request.put("provider_config", providerConfig);
    }

    /** user_role → clearance 映射（Python 侧等级模型：admin 全 clearance，其余 general）。 */
    private String mapClearance(String userRole) {
        return "admin".equalsIgnoreCase(userRole) ? "admin" : "general";
    }

    private void addInternalToken(HttpHeaders headers) {
        if (internalApiToken == null || internalApiToken.isBlank()) {
            throw new BusinessException(StatusCode.INTERNAL_ERROR, "PYTHON_AI_INTERNAL_TOKEN 未配置");
        }
        headers.set("X-Internal-Token", internalApiToken);
        // Propagate distributed trace ID to Python AI service
        String traceId = com.hfusionhub.config.TraceContext.getTraceId();
        if (traceId != null) {
            headers.set(com.hfusionhub.config.TraceContext.HEADER_NAME, traceId);
        }
        // Propagate tenant context to Python AI
        Long tenantId = com.hfusionhub.tenant.TenantContext.getTenantId();
        if (tenantId != null) {
            headers.set("X-Tenant-Id", tenantId.toString());
        }
    }

    /**
     * Chat response data model — Agent V1.
     *
     * Java-compat keys (consumed by Jackson from Python JSON):
     *   content, model, token_count, steps, sources, auto_detected_kb_id
     *
     * Agent V1 keys (available when calling /api/agent/v1/chat):
     *   answer, status, agent_run_id, token_usage, tool_calls_count,
     *   style_used, max_tool_steps, error_detail, failed_tool
     */
    public static class ChatResponse {
        // ── Java-compat ──
        private String content;
        private String model;

        @JsonProperty("token_count")
        private int tokenCount;

        private List<Map<String, Object>> steps;
        private List<Map<String, Object>> sources;

        @JsonProperty("auto_detected_kb_id")
        private Long autoDetectedKbId;

        // ── Agent V1 ──
        private String answer;
        private String status;

        @JsonProperty("agent_run_id")
        private String agentRunId;

        @JsonProperty("token_usage")
        private Map<String, Object> tokenUsage;

        @JsonProperty("tool_calls_count")
        private int toolCallsCount;

        @JsonProperty("style_used")
        private String styleUsed;

        @JsonProperty("max_tool_steps")
        private int maxToolSteps;

        @JsonProperty("error_detail")
        private String errorDetail;

        @JsonProperty("failed_tool")
        private String failedTool;

        @JsonProperty("step_events")
        private List<Map<String, Object>> stepEvents;

        public ChatResponse() {}

        // ── Java-compat getters/setters ──
        public String getContent() {
            return content;
        }

        public void setContent(String content) {
            this.content = content;
        }

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }

        public int getTokenCount() {
            return tokenCount;
        }

        public void setTokenCount(int tokenCount) {
            this.tokenCount = tokenCount;
        }

        public List<Map<String, Object>> getSteps() {
            return steps;
        }

        public void setSteps(List<Map<String, Object>> steps) {
            this.steps = steps;
        }

        public List<Map<String, Object>> getSources() {
            return sources;
        }

        public void setSources(List<Map<String, Object>> sources) {
            this.sources = sources;
        }

        public Long getAutoDetectedKbId() {
            return autoDetectedKbId;
        }

        public void setAutoDetectedKbId(Long autoDetectedKbId) {
            this.autoDetectedKbId = autoDetectedKbId;
        }

        // ── Agent V1 getters/setters ──
        public String getAnswer() {
            return answer;
        }

        public void setAnswer(String answer) {
            this.answer = answer;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getAgentRunId() {
            return agentRunId;
        }

        public void setAgentRunId(String agentRunId) {
            this.agentRunId = agentRunId;
        }

        public Map<String, Object> getTokenUsage() {
            return tokenUsage;
        }

        public void setTokenUsage(Map<String, Object> tokenUsage) {
            this.tokenUsage = tokenUsage;
        }

        public int getToolCallsCount() {
            return toolCallsCount;
        }

        public void setToolCallsCount(int toolCallsCount) {
            this.toolCallsCount = toolCallsCount;
        }

        public String getStyleUsed() {
            return styleUsed;
        }

        public void setStyleUsed(String styleUsed) {
            this.styleUsed = styleUsed;
        }

        public int getMaxToolSteps() {
            return maxToolSteps;
        }

        public void setMaxToolSteps(int maxToolSteps) {
            this.maxToolSteps = maxToolSteps;
        }

        public String getErrorDetail() {
            return errorDetail;
        }

        public void setErrorDetail(String errorDetail) {
            this.errorDetail = errorDetail;
        }

        public String getFailedTool() {
            return failedTool;
        }

        public void setFailedTool(String failedTool) {
            this.failedTool = failedTool;
        }

        public List<Map<String, Object>> getStepEvents() {
            return stepEvents;
        }

        public void setStepEvents(List<Map<String, Object>> stepEvents) {
            this.stepEvents = stepEvents;
        }
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

        public String getContent() {
            return content;
        }

        public String getRequestId() {
            return requestId;
        }
    }
}
