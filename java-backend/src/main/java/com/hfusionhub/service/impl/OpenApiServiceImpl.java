package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.RedisUtils;
import com.hfusionhub.dto.OpenApiChatRequest;
import com.hfusionhub.dto.OpenApiChatResponse;
import com.hfusionhub.entity.App;
import com.hfusionhub.entity.AppApiKey;
import com.hfusionhub.entity.AppCallLog;
import com.hfusionhub.entity.ModelUsageRecord;
import com.hfusionhub.mapper.AppApiKeyMapper;
import com.hfusionhub.mapper.AppCallLogMapper;
import com.hfusionhub.mapper.AppMapper;
import com.hfusionhub.service.CostTrackingService;
import com.hfusionhub.service.OpenApiService;
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

    /** 每 Key 每分钟最大调用次数（C4 限流） */
    private static final int RATE_LIMIT_PER_MINUTE = 60;

    private static final String RATE_LIMIT_KEY_PREFIX = "appkey:rl:";

    @Override
    public OpenApiChatResponse chat(String apiKey, OpenApiChatRequest request) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new BusinessException(401, "缺少 API Key（Authorization: Bearer <key> 或 X-API-Key）");
        }
        if (request.getQuery() == null || request.getQuery().isBlank()) {
            throw new BusinessException(400, "query 不能为空");
        }
        if (request.getQuery().length() > 4000) {
            throw new BusinessException(400, "query 长度不能超过 4000");
        }

        // 1. 解析 Key → 应用
        String hash = sha256Hex(apiKey.trim());
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
