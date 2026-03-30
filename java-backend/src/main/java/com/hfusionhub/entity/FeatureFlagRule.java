package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
@TableName("feature_flag_rule")
@Schema(description = "Per-scope override rule for a feature flag")
public class FeatureFlagRule extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "Rule ID")
    private Long id;

    @Schema(description = "FK to feature_flag.id")
    private Long flagId;

    @Schema(description = "Override scope: global, tenant, user, kb, environment")
    private String scope;

    @Schema(description = "Scope value (tenant_id, user_id, kb_id, env name)")
    private String scopeValue;

    @Schema(description = "Overridden enabled state")
    private Boolean enabled;

    @Schema(description = "Override percentage (0-100)")
    private Integer percentage;

    @Schema(description = "Override whitelist JSON array")
    private String whitelist;

    @Schema(description = "Override blacklist JSON array")
    private String blacklist;
}
