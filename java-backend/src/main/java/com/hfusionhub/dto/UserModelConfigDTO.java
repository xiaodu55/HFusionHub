package com.hfusionhub.dto;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class UserModelConfigDTO {
    private boolean configured;
    private String providerType;
    private String providerName;
    private String baseUrl;
    private String modelName;
    private boolean apiKeyConfigured;
    private boolean enabled;
    private String lastTestStatus;
    private String lastTestMessage;
    private LocalDateTime lastTestedAt;
    private LocalDateTime updatedAt;
}

