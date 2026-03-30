package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
@Schema(description = "Evaluate feature flag for a given context")
public class FeatureFlagEvaluateDTO {

    @NotBlank(message = "flagKey is required")
    @Schema(description = "Flag key to evaluate")
    private String flagKey;

    @Schema(description = "User ID (for user-level override)")
    private Long userId;

    @Schema(description = "Knowledge base ID (for KB-level override)")
    private Long knowledgeBaseId;

    @Schema(description = "Tenant ID (for tenant-level override)")
    private Long tenantId;

    @Schema(description = "Environment name (for environment-level override)")
    private String environment;
}
