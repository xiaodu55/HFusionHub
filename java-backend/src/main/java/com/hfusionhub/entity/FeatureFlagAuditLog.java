package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.io.Serializable;
import java.time.LocalDateTime;
import lombok.Data;

@Data
@TableName("feature_flag_audit_log")
@Schema(description = "Audit trail for feature flag changes")
public class FeatureFlagAuditLog implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(type = IdType.AUTO)
    @Schema(description = "Log ID")
    private Long id;

    @Schema(description = "FK to feature_flag.id")
    private Long flagId;

    @Schema(description = "Flag key at time of change")
    private String flagKey;

    @Schema(description = "Action: create, update, delete")
    private String action;

    @Schema(description = "User ID who made the change")
    private Long operatorId;

    @Schema(description = "JSON snapshot before change")
    private String oldValue;

    @Schema(description = "JSON snapshot after change")
    private String newValue;

    @Schema(description = "Reason for the change")
    private String reason;

    @Schema(description = "Creation time")
    private LocalDateTime createdAt;
}
