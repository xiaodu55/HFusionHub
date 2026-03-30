package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
@Schema(description = "Create feature flag rule request")
public class FeatureFlagRuleCreateDTO {

    @NotBlank(message = "scope is required")
    @Schema(description = "global | tenant | user | kb | environment")
    private String scope;

    @Schema(description = "Scope value (null for global)")
    private String scopeValue;

    @Schema(description = "Enabled state")
    private Boolean enabled;

    @Schema(description = "Percentage override")
    private Integer percentage;

    @Schema(description = "Whitelist override")
    private String whitelist;

    @Schema(description = "Blacklist override")
    private String blacklist;
}
