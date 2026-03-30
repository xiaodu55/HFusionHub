package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Data
@Schema(description = "Feature flag with rules")
public class FeatureFlagInfoDTO {

    @Schema(description = "Flag ID")
    private Long id;

    @Schema(description = "Flag key")
    private String flagKey;

    @Schema(description = "Flag type")
    private String flagType;

    @Schema(description = "Description")
    private String description;

    @Schema(description = "Global enabled state")
    private Boolean enabled;

    @Schema(description = "Percentage")
    private Integer percentage;

    @Schema(description = "Whitelist JSON")
    private String whitelist;

    @Schema(description = "Blacklist JSON")
    private String blacklist;

    @Schema(description = "Effective start")
    private LocalDateTime startTime;

    @Schema(description = "Effective end")
    private LocalDateTime endTime;

    @Schema(description = "Override rules")
    private List<FeatureFlagRuleInfoDTO> rules;

    @Schema(description = "Created at")
    private LocalDateTime createdAt;

    @Schema(description = "Updated at")
    private LocalDateTime updatedAt;
}
