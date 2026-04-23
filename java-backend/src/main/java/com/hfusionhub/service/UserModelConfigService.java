package com.hfusionhub.service;

import com.hfusionhub.dto.UserModelConfigDTO;
import com.hfusionhub.dto.UserModelConfigSaveDTO;
import java.util.Map;

public interface UserModelConfigService {
    UserModelConfigDTO get(Long userId);

    UserModelConfigDTO save(Long userId, UserModelConfigSaveDTO dto);

    void reset(Long userId);

    Map<String, Object> getRuntimeConfig(Long userId);

    Map<String, Object> resolveRuntimeConfig(Long userId, UserModelConfigSaveDTO dto);

    void recordTestResult(Long userId, boolean success, String message);
}
