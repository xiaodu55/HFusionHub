package com.hfusionhub.common.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

@Data
@Schema(description = "Update feature flag request")
public class FeatureFlagUpdateDTO {

    @Schema(description = "boolean | percentage | whitelist | blacklist")
    private String flagType;

    @Schema(description = "Description")
    private String description;

    @Schema(description = "Global enabled state")
    private Boolean enabled;

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

    @Schema(description = "Reason for change")
    private String reason;
}
