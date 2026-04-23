package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
@TableName("feature_flag")
@Schema(description = "Feature flag definition")
public class FeatureFlag extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "Flag ID")
    private Long id;

    @Schema(description = "Unique flag key, e.g. agent.enabled")
    private String flagKey;

    @Schema(description = "boolean | percentage | whitelist | blacklist")
    private String flagType;

    @Schema(description = "Human-readable description")
    private String description;

    @Schema(description = "Global enabled state")
    private Boolean enabled;

    @Schema(description = "Percentage (0-100) for percentage rollout")
    private Integer percentage;

    @Schema(description = "JSON array of IDs for whitelist")
    private String whitelist;

    @Schema(description = "JSON array of IDs for blacklist")
    private String blacklist;

    @Schema(description = "Effective start time (null = always)")
    private LocalDateTime startTime;

    @Schema(description = "Effective end time (null = always)")
    private LocalDateTime endTime;
}
