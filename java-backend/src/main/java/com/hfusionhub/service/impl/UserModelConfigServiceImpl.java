package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.ModelCredentialCipher;
import com.hfusionhub.dto.UserModelConfigDTO;
import com.hfusionhub.dto.UserModelConfigSaveDTO;
import com.hfusionhub.entity.UserModelConfig;
import com.hfusionhub.mapper.UserModelConfigMapper;
import com.hfusionhub.service.UserModelConfigService;
import java.net.URI;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Service
@RequiredArgsConstructor
public class UserModelConfigServiceImpl implements UserModelConfigService {

    private static final Set<String> PROVIDER_TYPES = Set.of("openai_compatible", "ollama");
    private static final String CACHE_KEY_PREFIX = "user_model_config:";
    private static final long CACHE_TTL_SECONDS = 60;

    private final UserModelConfigMapper mapper;
    private final ModelCredentialCipher cipher;
    private final RedisTemplate<String, Object> redisTemplate;

    @Override
    public UserModelConfigDTO get(Long userId) {
        UserModelConfig config = find(userId);
        if (config == null) {
            return UserModelConfigDTO.builder()
                    .configured(false)
                    .providerType("system")
                    .providerName("系统默认")
                    .enabled(false)
                    .apiKeyConfigured(false)
                    .build();
        }
        return toDTO(config);
    }

    @Override
    @Transactional
    public UserModelConfigDTO save(Long userId, UserModelConfigSaveDTO dto) {
        requireUser(userId);
        validate(dto);
        UserModelConfig config = find(userId);
        boolean creating = config == null;
        if (creating) {
            config = new UserModelConfig();
            config.setUserId(userId);
        }

        String normalizedBaseUrl = normalizeBaseUrl(dto.getBaseUrl());
        boolean sameEndpoint = !creating
                && dto.getProviderType().equals(config.getProviderType())
                && normalizedBaseUrl.equals(config.getBaseUrl());

        config.setProviderType(dto.getProviderType());
        config.setProviderName(dto.getProviderName().trim());
        config.setBaseUrl(normalizedBaseUrl);
        config.setModelName(dto.getModelName().trim());
        config.setEnabled(Boolean.FALSE.equals(dto.getEnabled()) ? 0 : 1);

        if ("ollama".equals(dto.getProviderType())) {
            config.setApiKeyCiphertext(null);
        } else if (StringUtils.hasText(dto.getApiKey())) {
            config.setApiKeyCiphertext(cipher.encrypt(dto.getApiKey().trim()));
        } else if (!sameEndpoint || !StringUtils.hasText(config.getApiKeyCiphertext())) {
            throw new BusinessException("首次配置或更换 Base URL 时必须重新填写 API Key");
        }

        config.setLastTestStatus(null);
        config.setLastTestMessage(null);
        config.setLastTestedAt(null);
        if (creating) mapper.insert(config);
        else mapper.updateById(config);

        // Invalidate cache on save
        evictCache(userId);

        return toDTO(config);
    }

    @Override
    @Transactional
    public void reset(Long userId) {
        UserModelConfig config = find(userId);
        if (config != null) {
            mapper.deleteById(config.getId());
            evictCache(userId);
        }
    }

    @Override
    public Map<String, Object> getRuntimeConfig(Long userId) {
        if (userId == null || userId <= 0) return Map.of();

        // Try cache first
        String cacheKey = CACHE_KEY_PREFIX + userId;
        @SuppressWarnings("unchecked")
        Map<String, Object> cached = (Map<String, Object>) redisTemplate.opsForValue().get(cacheKey);
        if (cached != null) {
            return cached;
        }

        // Cache miss: query DB + decrypt
        UserModelConfig config = find(userId);
        if (config == null || !Integer.valueOf(1).equals(config.getEnabled())) {
            return Map.of();
        }

        Map<String, Object> runtimeConfig = runtimeMap(
                config.getProviderType(),
                config.getProviderName(),
                config.getBaseUrl(),
                config.getModelName(),
                cipher.decrypt(config.getApiKeyCiphertext()));

        // Cache for 60s
        redisTemplate.opsForValue().set(cacheKey, runtimeConfig, CACHE_TTL_SECONDS, TimeUnit.SECONDS);
        return runtimeConfig;
    }

    @Override
    public Map<String, Object> resolveRuntimeConfig(Long userId, UserModelConfigSaveDTO dto) {
        requireUser(userId);
        validate(dto);
        String apiKey = StringUtils.hasText(dto.getApiKey()) ? dto.getApiKey().trim() : null;
        if (!"ollama".equals(dto.getProviderType()) && !StringUtils.hasText(apiKey)) {
            UserModelConfig existing = find(userId);
            String normalizedBaseUrl = normalizeBaseUrl(dto.getBaseUrl());
            boolean sameEndpoint = existing != null
                    && dto.getProviderType().equals(existing.getProviderType())
                    && normalizedBaseUrl.equals(existing.getBaseUrl());
            if (sameEndpoint && StringUtils.hasText(existing.getApiKeyCiphertext())) {
                apiKey = cipher.decrypt(existing.getApiKeyCiphertext());
            } else {
                throw new BusinessException("首次配置或更换 Base URL 时，请填写 API Key 后再测试连接");
            }
        }
        return runtimeMap(
                dto.getProviderType(),
                dto.getProviderName().trim(),
                normalizeBaseUrl(dto.getBaseUrl()),
                dto.getModelName().trim(),
                apiKey);
    }

    @Override
    public void recordTestResult(Long userId, boolean success, String message) {
        UserModelConfig config = find(userId);
        if (config == null) return;
        config.setLastTestStatus(success ? "success" : "failed");
        config.setLastTestMessage(cleanMessage(message));
        config.setLastTestedAt(LocalDateTime.now());
        mapper.updateById(config);
    }

    private UserModelConfig find(Long userId) {
        if (userId == null) return null;
        return mapper.selectOne(new LambdaQueryWrapper<UserModelConfig>()
                .eq(UserModelConfig::getUserId, userId)
                .last("LIMIT 1"));
    }

    private void validate(UserModelConfigSaveDTO dto) {
        if (dto == null || !PROVIDER_TYPES.contains(dto.getProviderType())) {
            throw new BusinessException("请选择 OpenAI 兼容接口或 Ollama");
        }
        normalizeBaseUrl(dto.getBaseUrl());
    }

    private String normalizeBaseUrl(String raw) {
        try {
            String value = raw == null ? "" : raw.trim();
            URI uri = URI.create(value);
            if (!("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme()))
                    || !StringUtils.hasText(uri.getHost())
                    || uri.getUserInfo() != null) {
                throw new IllegalArgumentException("invalid URL");
            }
            while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
            return value;
        } catch (Exception e) {
            throw new BusinessException("Base URL 格式不正确，请填写完整的 http:// 或 https:// 地址");
        }
    }

    private Map<String, Object> runtimeMap(String type, String name, String baseUrl, String model, String apiKey) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("provider_type", type);
        result.put("provider_name", name);
        result.put("base_url", baseUrl);
        result.put("model", model);
        if (StringUtils.hasText(apiKey)) result.put("api_key", apiKey);
        return result;
    }

    private UserModelConfigDTO toDTO(UserModelConfig config) {
        return UserModelConfigDTO.builder()
                .configured(true)
                .providerType(config.getProviderType())
                .providerName(config.getProviderName())
                .baseUrl(config.getBaseUrl())
                .modelName(config.getModelName())
                .apiKeyConfigured(StringUtils.hasText(config.getApiKeyCiphertext()))
                .enabled(Integer.valueOf(1).equals(config.getEnabled()))
                .lastTestStatus(config.getLastTestStatus())
                .lastTestMessage(config.getLastTestMessage())
                .lastTestedAt(config.getLastTestedAt())
                .updatedAt(config.getUpdatedAt())
                .build();
    }

    private String cleanMessage(String message) {
        if (!StringUtils.hasText(message)) return null;
        String clean = message.replaceAll("(?i)(bearer\\s+)[^\\s]+", "$1***").replaceAll("sk-[A-Za-z0-9_-]+", "sk-***");
        return clean.length() > 500 ? clean.substring(0, 500) : clean;
    }

    private void requireUser(Long userId) {
        if (userId == null || userId <= 0) throw new BusinessException("无法识别当前登录用户");
    }

    private void evictCache(Long userId) {
        if (userId != null && userId > 0) {
            redisTemplate.delete(CACHE_KEY_PREFIX + userId);
        }
    }
}
