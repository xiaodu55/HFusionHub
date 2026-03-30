package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
@Schema(description = "Feature flag evaluation result")
public class FeatureFlagEvaluateResultDTO {

    @Schema(description = "Flag key")
    private String flagKey;

    @Schema(description = "Whether the flag is enabled for this context")
    private boolean enabled;

    @Schema(description = "Which scope provided the final value")
    private String matchedScope;

    @Schema(description = "Rule ID that was applied (null if global default)")
    private Long matchedRuleId;

    @Schema(description = "Reason the flag was evaluated this way")
    private String reason;
}
