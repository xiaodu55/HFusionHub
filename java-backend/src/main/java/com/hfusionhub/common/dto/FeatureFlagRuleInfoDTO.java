package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Data
@Schema(description = "Feature flag rule info")
public class FeatureFlagRuleInfoDTO {

    @Schema(description = "Rule ID")
    private Long id;

    @Schema(description = "Parent flag ID")
    private Long flagId;

    @Schema(description = "Scope: global, tenant, user, kb, environment")
    private String scope;

    @Schema(description = "Scope value")
    private String scopeValue;

    @Schema(description = "Overridden enabled state")
    private Boolean enabled;

    @Schema(description = "Override percentage")
    private Integer percentage;

    @Schema(description = "Override whitelist")
    private String whitelist;

    @Schema(description = "Override blacklist")
    private String blacklist;
}
