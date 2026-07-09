package com.hfusionhub.controller;

import com.hfusionhub.dto.OpenApiBidCheckRequest;
import com.hfusionhub.dto.OpenApiBidCheckResponse;
import com.hfusionhub.dto.OpenApiChatRequest;
import com.hfusionhub.dto.OpenApiChatResponse;
import com.hfusionhub.service.OpenApiService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 开放 API — 无需登录，使用应用 API Key 鉴权。
 *
 * <p>调用方式：{@code Authorization: Bearer hf_xxx} 或 {@code X-API-Key: hf_xxx}。
 * 该路径已在 SaTokenConfig 中排除登录拦截，鉴权由 {@link OpenApiService} 完成。</p>
 *
 * @author HFusionHub Team
 */
@Tag(name = "开放 API", description = "通过应用 API Key 调用已发布的应用")
@RestController
@RequestMapping("/openapi")
@RequiredArgsConstructor
public class OpenApiController {

    private final OpenApiService openApiService;

    @Operation(summary = "应用对话", description = "使用已发布应用的 API Key 发起一次对话")
    @PostMapping("/chat")
    public OpenApiChatResponse chat(
            @RequestHeader(value = "Authorization", required = false) String authorization,
            @RequestHeader(value = "X-API-Key", required = false) String apiKeyHeader,
            @RequestBody OpenApiChatRequest request) {
        String apiKey = extractApiKey(authorization, apiKeyHeader);
        return openApiService.chat(apiKey, request);
    }

    @Operation(summary = "应用对话流式", description = "使用已发布应用的 API Key 发起 SSE 流式对话（Batch 6，需应用绑定知识库）")
    @PostMapping("/chat/stream")
    public org.springframework.web.servlet.mvc.method.annotation.SseEmitter chatStream(
            @RequestHeader(value = "Authorization", required = false) String authorization,
            @RequestHeader(value = "X-API-Key", required = false) String apiKeyHeader,
            @RequestBody OpenApiChatRequest request) {
        String apiKey = extractApiKey(authorization, apiKeyHeader);
        org.springframework.web.servlet.mvc.method.annotation.SseEmitter emitter =
                new org.springframework.web.servlet.mvc.method.annotation.SseEmitter(120_000L);
        openApiService.chatStream(apiKey, request, emitter);
        return emitter;
    }

    @Operation(summary = "投标废标自检", description = "使用已发布应用的 API Key 对租户投标项目执行废标自检（P2-7，需开通 openapi 模块）")
    @PostMapping("/bid/check")
    public OpenApiBidCheckResponse bidCheck(
            @RequestHeader(value = "Authorization", required = false) String authorization,
            @RequestHeader(value = "X-API-Key", required = false) String apiKeyHeader,
            @RequestBody OpenApiBidCheckRequest request) {
        String apiKey = extractApiKey(authorization, apiKeyHeader);
        return openApiService.bidCheck(apiKey, request.getProjectId());
    }

    private String extractApiKey(String authorization, String apiKeyHeader) {
        if (authorization != null && authorization.startsWith("Bearer ")) {
            return authorization.substring("Bearer ".length()).trim();
        }
        if (apiKeyHeader != null && !apiKeyHeader.isBlank()) {
            return apiKeyHeader.trim();
        }
        return null;
    }
}
