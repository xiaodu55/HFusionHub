package com.hfusionhub.service.impl;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.ModelCredentialCipher;
import com.hfusionhub.dto.UserModelConfigDTO;
import com.hfusionhub.dto.UserModelConfigSaveDTO;
import com.hfusionhub.mapper.UserModelConfigMapper;
import com.hfusionhub.entity.UserModelConfig;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class UserModelConfigServiceImplTest {

    @Mock
    private UserModelConfigMapper mapper;
    @Mock
    private ModelCredentialCipher cipher;

    private UserModelConfigServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new UserModelConfigServiceImpl(mapper, cipher);
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
