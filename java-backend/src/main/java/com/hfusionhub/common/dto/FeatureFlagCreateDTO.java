package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import java.time.LocalDateTime;
import lombok.Data;

@Data
@Schema(description = "Create feature flag request")
public class FeatureFlagCreateDTO {

    @NotBlank(message = "flagKey is required")
    @Pattern(regexp = "^[a-z][a-z0-9.]*$", message = "flagKey: lowercase letters, digits, dots only")
    @Schema(description = "Unique flag key")
    private String flagKey;

    @Schema(description = "boolean | percentage | whitelist | blacklist", defaultValue = "boolean")
    private String flagType = "boolean";

    @Schema(description = "Description")
    private String description;

    @Schema(description = "Global enabled state")
    private Boolean enabled = false;

    @Schema(description = "Percentage (0-100)")
    private Integer percentage;

    @Schema(description = "Whitelist JSON array")
    private String whitelist;

    @Schema(description = "Blacklist JSON array")
    private String blacklist;

    @Schema(description = "Effective start time")
    private LocalDateTime startTime;

    @Schema(description = "Effective end time")
    private LocalDateTime endTime;

    @Schema(description = "Reason for creation")
    private String reason;
}
