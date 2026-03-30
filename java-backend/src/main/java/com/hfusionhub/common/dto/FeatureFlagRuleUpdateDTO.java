package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Data
@Schema(description = "Update feature flag rule request")
public class FeatureFlagRuleUpdateDTO {

    @Schema(description = "Scope")
    private String scope;

    @Schema(description = "Scope value")
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
