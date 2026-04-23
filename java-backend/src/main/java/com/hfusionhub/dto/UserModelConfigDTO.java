package com.hfusionhub.dto;

import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Data;

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
