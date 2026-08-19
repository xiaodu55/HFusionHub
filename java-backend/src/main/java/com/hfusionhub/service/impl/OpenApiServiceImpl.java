package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.RedisUtils;
import com.hfusionhub.dto.OpenApiBidCheckResponse;
import com.hfusionhub.dto.OpenApiChatRequest;
import com.hfusionhub.dto.OpenApiChatResponse;
import com.hfusionhub.entity.App;
import com.hfusionhub.entity.AppApiKey;
import com.hfusionhub.entity.AppCallLog;
import com.hfusionhub.entity.ModelUsageRecord;
import com.hfusionhub.mapper.AppApiKeyMapper;
import com.hfusionhub.mapper.AppCallLogMapper;
import com.hfusionhub.mapper.AppMapper;
import com.hfusionhub.service.BidCheckService;
import com.hfusionhub.service.CostTrackingService;
import com.hfusionhub.service.OpenApiService;
import com.hfusionhub.tenant.TenantContext;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

/**
 * 开放 API 对话服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class OpenApiServiceImpl implements OpenApiService {

    private final AppMapper appMapper;
    private final AppApiKeyMapper apiKeyMapper;
    private final AppCallLogMapper callLogMapper;
    private final AiClient aiClient;
    private final RedisUtils redisUtils;
    private final CostTrackingService costTrackingService;
    private final BidCheckService bidCheckService;

    /** 每 Key 每分钟最大调用次数（C4 限流） */
    private static final int RATE_LIMIT_PER_MINUTE = 60;

    private static final String RATE_LIMIT_KEY_PREFIX = "appkey:rl:";

    @Override
    public OpenApiChatResponse chat(String apiKey, OpenApiChatRequest request) {
        if (request.getQuery() == null || request.getQuery().isBlank()) {
            throw new BusinessException(400, "query 不能为空");
        }
        if (request.getQuery().length() > 4000) {
            throw new BusinessException(400, "query 长度不能超过 4000");
        }

        // 1. 解析 Key → 应用
        ResolvedKey resolved = resolvePublishedApp(apiKey);
        App app = resolved.app();
        AppApiKey key = resolved.key();

        // 2. 限流（Redis 固定窗口，失败放行并记录日志）
        if (!allow(key.getId())) {
            recordCall(app, key, "rate_limited", 0, 0, 0);
            throw new BusinessException(429, "调用频率超限，请稍后重试");
        }

        // 3. 调用 AI（以应用所有者身份，绑定应用知识库）
        OpenApiChatResponse response = new OpenApiChatResponse();
        int promptTokens = 0;
        int completionTokens = 0;
        int totalTokens = 0;
        try {
            AiClient.ChatResponse ai;
            if (app.getKnowledgeBaseId() != null && app.getKnowledgeBaseId() > 0) {
                ai = aiClient.agentV1Chat(
                        request.getQuery(),
                        null,
                        app.getKnowledgeBaseId(),
                        request.getHistory(),
                        app.getStyle() == null ? "detailed" : app.getStyle(),
                        5,
                        "openapi-" + UUID.randomUUID(),
                        app.getUserId(),
                        null,
                        "user");
            } else {
                ai = aiClient.chat(
                        request.getQuery(),
                        null,
                        null,
                        request.getHistory(),
                        app.getStyle() == null ? "detailed" : app.getStyle(),
                        5);
            }
            response.setContent(ai.getContent());
            response.setSources(ai.getSources());
            response.setModel(ai.getModel());
            response.setStatus(ai.getStatus());
            response.setTokenUsage(
                    ai.getTokenUsage() != null ? ai.getTokenUsage() : Map.of("total_tokens", ai.getTokenCount()));
            Map<String, Object> usage = ai.getTokenUsage();
            promptTokens = intVal(usage, "prompt_tokens", 0);
            completionTokens = intVal(usage, "completion_tokens", 0);
            totalTokens = intVal(usage, "total_tokens", ai.getTokenCount());
        } catch (Exception e) {
            recordCall(app, key, "error", 0, 0, 0);
            log.warn("开放 API 调用失败: app={}, key={}, err={}", app.getId(), key.getId(), e.getMessage());
            throw e;
        }

        recordCall(app, key, "ok", promptTokens, completionTokens, totalTokens);
        return response;
    }

    @Override
    public void chatStream(String apiKey, OpenApiChatRequest request,
                           org.springframework.web.servlet.mvc.method.annotation.SseEmitter emitter) {
        if (request.getQuery() == null || request.getQuery().isBlank()) {
            throw new BusinessException(400, "query 不能为空");
        }
        if (request.getQuery().length() > 4000) {
            throw new BusinessException(400, "query 长度不能超过 4000");
        }

        ResolvedKey resolved = resolvePublishedApp(apiKey);
        App app = resolved.app();
        AppApiKey key = resolved.key();

        if (!allow(key.getId())) {
            recordCall(app, key, "rate_limited", 0, 0, 0);
            throw new BusinessException(429, "调用频率超限，请稍后重试");
        }
        if (app.getKnowledgeBaseId() == null || app.getKnowledgeBaseId() <= 0) {
            recordCall(app, key, "error", 0, 0, 0);
            throw new BusinessException(400, "流式对话要求应用绑定知识库（Agent V1 通道）");
        }

        String requestId = "openapi-" + UUID.randomUUID();
        int[] usage = new int[3]; // prompt, completion, total
        com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();

        try {
            aiClient.agentV1ChatStream(
                            request.getQuery(),
                            null,
                            app.getKnowledgeBaseId(),
                            request.getHistory(),
                            requestId,
                            app.getUserId(),
                            null,
                            null,
                            null,
                            // OpenApi 以应用所有者身份调用；与同步链路一致取
                            // fail-closed 的 user clearance（admin 走会话聊天）
                            "user")
                    .doOnNext(chunk -> {
                        try {
                            emitter.send(org.springframework.web.servlet.mvc.method.annotation.SseEmitter
                                    .event().data(chunk));
                        } catch (java.io.IOException io) {
                            throw new RuntimeException(io);
                        }
                        // run_completed 事件携带 token_usage —— 提取用于计费
                        try {
                            java.util.Map<?, ?> event = mapper.readValue(chunk, java.util.Map.class);
                            if ("run_completed".equals(event.get("event"))) {
                                Object usageObj = event.get("token_usage");
                                if (usageObj instanceof java.util.Map<?, ?> usageMap) {
                                    usage[0] = intOf(usageMap.get("prompt_tokens"));
                                    usage[1] = intOf(usageMap.get("completion_tokens"));
                                    usage[2] = intOf(usageMap.get("total_tokens"));
                                }
                            }
                        } catch (Exception ignored) {
                            // 非 JSON chunk（如 [DONE]）直接跳过
                        }
                    })
                    .doOnError(e -> {
                        recordCall(app, key, "error", 0, 0, 0);
                        log.warn("开放 API 流式调用失败: app={}, key={}, err={}",
                                app.getId(), key.getId(), e.getMessage());
                        emitter.completeWithError(e);
                    })
                    .doOnComplete(() -> {
                        try {
                            emitter.send(org.springframework.web.servlet.mvc.method.annotation.SseEmitter
                                    .event().data("[DONE]"));
                        } catch (java.io.IOException ignored) {
                            // 客户端已断开
                        }
                        emitter.complete();
                        recordCall(app, key, "ok", usage[0], usage[1], usage[2]);
                    })
                    .subscribe();
        } catch (Exception e) {
            recordCall(app, key, "error", 0, 0, 0);
            throw e;
        }
    }

    @Override
    public OpenApiBidCheckResponse bidCheck(String apiKey, Long projectId) {
        if (projectId == null) {
            throw new BusinessException(400, "project_id 不能为空");
        }

        // 1. 解析 Key → 应用
        ResolvedKey resolved = resolvePublishedApp(apiKey);
        App app = resolved.app();
        AppApiKey key = resolved.key();

        // 2. 限流（Redis 固定窗口，失败放行并记录日志）
        if (!allow(key.getId())) {
            recordCall(app, key, "rate_limited", 0, 0, 0);
            throw new BusinessException(429, "调用频率超限，请稍后重试");
        }

        // 3. 以应用所有者租户上下文执行废标自检（openapi 模块开关在 checkForApi 内校验）
        Long tenantId = app.getTenantId();
        if (tenantId == null) {
            recordCall(app, key, "error", 0, 0, 0);
            throw new BusinessException(403, "应用未归属租户，无法调用投标自检");
        }
        try {
            Map<String, Object> summary = TenantContext.runAs(tenantId,
                    () -> bidCheckService.checkForApi(projectId, tenantId));
            OpenApiBidCheckResponse response = new OpenApiBidCheckResponse();
            response.setStatus("ok");
            response.setProjectId(projectId);
            response.setSummary(summary);
            recordCall(app, key, "ok", 0, 0, 0);
            return response;
        } catch (BusinessException e) {
            recordCall(app, key, "error", 0, 0, 0);
            throw e;
        }
    }

    private record ResolvedKey(App app, AppApiKey key) {}

    /** 解析 API Key → 已发布应用（401 无效 / 403 未发布） */
    private ResolvedKey resolvePublishedApp(String apiKey) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new BusinessException(401, "缺少 API Key（Authorization: Bearer <key> 或 X-API-Key）");
        }
        String hash = sha256Hex(apiKey.trim());
        // /openapi/** 不经过租户拦截器（外部调用无会话租户），此时租户行拦截器会把
        // tenant_id 缺省填充为 1，导致非 1 租户的 key 永远查不到（401）。
        // key_hash 全局唯一，解析属平台级查找 —— 以系统作用域执行，
        // 后续业务再按 app.tenantId 走 runAs（见 chat/bidCheck）。
        return TenantContext.runAsSystem(() -> {
            AppApiKey key = apiKeyMapper.selectOne(new LambdaQueryWrapper<AppApiKey>()
                    .eq(AppApiKey::getKeyHash, hash)
                    .eq(AppApiKey::getEnabled, 1));
            if (key == null) {
                throw new BusinessException(401, "API Key 无效或已停用");
            }
            App app = appMapper.selectById(key.getAppId());
            if (app == null || app.getStatus() == null || app.getStatus() != 1) {
                throw new BusinessException(403, "应用未发布或已停用");
            }
            return new ResolvedKey(app, key);
        });
    }

    private boolean allow(Long keyId) {
        try {
            String window = String.valueOf(System.currentTimeMillis() / 60_000L);
            String redisKey = RATE_LIMIT_KEY_PREFIX + keyId + ":" + window;
            Long count = redisUtils.increment(redisKey, 1);
            if (count != null && count == 1L) {
                redisUtils.expire(redisKey, 60, java.util.concurrent.TimeUnit.SECONDS);
            }
            return count == null || count <= RATE_LIMIT_PER_MINUTE;
        } catch (Exception e) {
            log.warn("限流检查失败，放行: {}", e.getMessage());
            return true; // fail-open with logging
        }
    }
    /** Number → int（null/非数值返回 0）。流式 token 提取用。 */
    private static int intOf(Object value) {
        return value instanceof Number number ? number.intValue() : 0;
    }


    private static int intVal(Map<String, Object> map, String key, int defaultValue) {
        if (map == null || !map.containsKey(key)) {
            return defaultValue;
        }
        Object value = map.get(key);
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        return defaultValue;
    }

    private void recordCall(App app, AppApiKey key, String status, int prompt, int completion, int total) {
        try {
            AppCallLog logEntry = new AppCallLog();
            logEntry.setAppId(app.getId());
            logEntry.setApiKeyId(key.getId());
            logEntry.setTenantId(app.getTenantId());
            logEntry.setStatus(status);
            logEntry.setPromptTokens(prompt);
            logEntry.setCompletionTokens(completion);
            logEntry.setTotalTokens(total);
            logEntry.setCreatedAt(LocalDateTime.now());
            callLogMapper.insert(logEntry);
        } catch (Exception e) {
            log.warn("应用调用记录写入失败: {}", e.getMessage());
        }
        // P3: 开放 API 用量同时落 model_usage_record（/cost 模型用量页可见）
        if ("ok".equals(status) && app.getUserId() != null) {
            try {
                ModelUsageRecord rec = new ModelUsageRecord();
                rec.setUserId(app.getUserId());
                rec.setTenantId(app.getTenantId());
                rec.setRequestType("openapi");
                rec.setModel(app.getModel() != null && !app.getModel().isBlank() ? app.getModel() : "unknown");
                rec.setProvider(rec.getModel());
                rec.setPromptTokens(prompt);
                rec.setCompletionTokens(completion);
                rec.setTotalTokens(total > 0 ? total : prompt + completion);
                rec.setCostUsd(java.math.BigDecimal.ZERO);
                rec.setLatencyMs(0);
                costTrackingService.record(rec);
            } catch (Exception e) {
                log.warn("开放 API 用量落账失败: {}", e.getMessage());
            }
        }
    }

    private static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 不可用", e);
        }
    }
}
