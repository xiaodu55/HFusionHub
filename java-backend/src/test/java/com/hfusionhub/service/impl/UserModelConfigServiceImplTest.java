package com.hfusionhub.service.impl;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.ModelCredentialCipher;
import com.hfusionhub.dto.UserModelConfigDTO;
import com.hfusionhub.dto.UserModelConfigSaveDTO;
import com.hfusionhub.entity.UserModelConfig;
import com.hfusionhub.mapper.UserModelConfigMapper;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

@ExtendWith(MockitoExtension.class)
class UserModelConfigServiceImplTest {

    @Mock
    private UserModelConfigMapper mapper;

    @Mock
    private ModelCredentialCipher cipher;

    @Mock
    private RedisTemplate<String, Object> redisTemplate;

    @Mock
    private ValueOperations<String, Object> valueOperations;

    private UserModelConfigServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new UserModelConfigServiceImpl(mapper, cipher, redisTemplate);
    }

    @Test
    void returnsSystemDefaultWhenUserHasNoPersonalConfig() {
        when(mapper.selectOne(any())).thenReturn(null);

        UserModelConfigDTO result = service.get(7L);

        assertThat(result.isConfigured()).isFalse();
        assertThat(result.getProviderType()).isEqualTo("system");
    }

    @Test
    void requiresApiKeyForFirstCloudProviderSave() {
        when(mapper.selectOne(any())).thenReturn(null);
        UserModelConfigSaveDTO dto = dto("openai_compatible", "https://api.example.com", "model-a");

        assertThatThrownBy(() -> service.save(7L, dto))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("API Key");
    }

    @Test
    void savesOllamaWithoutApiKey() {
        when(mapper.selectOne(any())).thenReturn(null);
        UserModelConfigSaveDTO dto = dto("ollama", "http://localhost:11434/", "qwen2.5:3b");

        UserModelConfigDTO result = service.save(7L, dto);

        assertThat(result.getBaseUrl()).isEqualTo("http://localhost:11434");
        assertThat(result.isEnabled()).isTrue();
        verify(mapper).insert(any());
    }

    @Test
    void doesNotReuseCloudKeyWhenBaseUrlChanges() {
        UserModelConfig existing = new UserModelConfig();
        existing.setId(10L);
        existing.setUserId(7L);
        existing.setProviderType("openai_compatible");
        existing.setBaseUrl("https://old.example.com");
        existing.setApiKeyCiphertext("encrypted");
        when(mapper.selectOne(any())).thenReturn(existing);
        UserModelConfigSaveDTO dto = dto("openai_compatible", "https://new.example.com", "model-a");

        assertThatThrownBy(() -> service.save(7L, dto))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("Base URL");
    }

    @Test
    void runtimeConfigIsCachedOnFirstCallAndReused() {
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        when(valueOperations.get("user_model_config:7")).thenReturn(null);
        UserModelConfig existing = config(7L);
        when(mapper.selectOne(any())).thenReturn(existing);
        when(cipher.decrypt("encrypted")).thenReturn("sk-real-key");

        Map<String, Object> first = service.getRuntimeConfig(7L);
        // Second call hits the cache (get returns the previously stored map)
        when(valueOperations.get("user_model_config:7")).thenReturn(first);
        Map<String, Object> second = service.getRuntimeConfig(7L);

        assertThat(first).containsEntry("model", "model-a").containsEntry("api_key", "sk-real-key");
        assertThat(second).isEqualTo(first);
        // DB + decrypt hit only once, second call served from cache
        verify(mapper).selectOne(any());
        verify(cipher).decrypt("encrypted");
        verify(valueOperations).set(eq("user_model_config:7"), eq(first), eq(60L), eq(TimeUnit.SECONDS));
    }

    @Test
    void runtimeConfigReturnsEmptyWhenNoConfigAndDoesNotCache() {
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        when(valueOperations.get("user_model_config:7")).thenReturn(null);
        when(mapper.selectOne(any())).thenReturn(null);

        Map<String, Object> result = service.getRuntimeConfig(7L);

        assertThat(result).isEmpty();
        verify(valueOperations, never()).set(any(), any(), anyLong(), any());
    }

    @Test
    void runtimeConfigReturnsEmptyWhenDisabled() {
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        when(valueOperations.get("user_model_config:7")).thenReturn(null);
        UserModelConfig existing = config(7L);
        existing.setEnabled(0);
        when(mapper.selectOne(any())).thenReturn(existing);

        Map<String, Object> result = service.getRuntimeConfig(7L);

        assertThat(result).isEmpty();
        verify(valueOperations, never()).set(any(), any(), anyLong(), any());
    }

    @Test
    void saveInvalidatesCache() {
        when(mapper.selectOne(any())).thenReturn(null);

        service.save(7L, dto("ollama", "http://localhost:11434/", "qwen2.5:3b"));

        verify(redisTemplate).delete("user_model_config:7");
    }

    @Test
    void resetInvalidatesCache() {
        UserModelConfig existing = config(7L);
        when(mapper.selectOne(any())).thenReturn(existing);

        service.reset(7L);

        verify(mapper).deleteById(existing.getId());
        verify(redisTemplate).delete("user_model_config:7");
    }

    private UserModelConfig config(Long userId) {
        UserModelConfig existing = new UserModelConfig();
        existing.setId(10L);
        existing.setUserId(userId);
        existing.setProviderType("openai_compatible");
        existing.setProviderName("Example");
        existing.setBaseUrl("https://api.example.com");
        existing.setModelName("model-a");
        existing.setEnabled(1);
        existing.setApiKeyCiphertext("encrypted");
        return existing;
    }

    private UserModelConfigSaveDTO dto(String type, String baseUrl, String model) {
        UserModelConfigSaveDTO dto = new UserModelConfigSaveDTO();
        dto.setProviderType(type);
        dto.setProviderName("Example");
        dto.setBaseUrl(baseUrl);
        dto.setModelName(model);
        dto.setEnabled(true);
        return dto;
    }
}
