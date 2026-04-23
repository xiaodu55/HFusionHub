package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 操作审计日志实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName("audit_log")
@Schema(description = "操作审计日志")
public class AuditLog {

    @TableId(type = IdType.AUTO)
    @Schema(description = "日志ID")
    private Long id;

    @Schema(description = "操作人")
    private Long operatorId;

    @Schema(description = "租户")
    private Long tenantId;

    @Schema(description = "动作")
    private String action;

    @Schema(description = "目标类型")
    private String targetType;

    @Schema(description = "目标ID")
    private String targetId;

    @Schema(description = "摘要")
    private String detail;

    @Schema(description = "时间")
    private LocalDateTime createdAt;
}
