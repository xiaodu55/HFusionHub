package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 跨租户代操作审计记录
 *
 * @author HFusionHub Team
 */
@Data
@TableName("tenant_audit_log")
@Schema(description = "跨租户代操作审计")
public class TenantAuditLog {

    @TableId(type = IdType.AUTO)
    @Schema(description = "ID")
    private Long id;

    @Schema(description = "平台管理员 user id")
    private Long operatorId;

    @Schema(description = "管理员自身租户")
    private Long fromTenant;

    @Schema(description = "代操作目标租户")
    private Long toTenant;

    @Schema(description = "HTTP 方法 + 路径")
    private String action;

    @Schema(description = "记录时间")
    private LocalDateTime createdAt;
}
