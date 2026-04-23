package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 插件审计日志实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName("plugin_audit_log")
@Schema(description = "插件审计日志")
public class PluginAuditLog {

    @TableId(type = IdType.AUTO)
    @Schema(description = "日志ID")
    private Long id;

    @Schema(description = "事件UUID（幂等键，来自 Python AI）")
    private String eventId;

    @Schema(description = "关联插件ID")
    private Long pluginId;

    @Schema(description = "插件名称")
    private String pluginName;

    @Schema(description = "操作: install|enable|disable|update|uninstall|rollback")
    private String action;

    @Schema(description = "操作人用户ID")
    private Long operatorId;

    @Schema(description = "旧值")
    private String oldValue;

    @Schema(description = "新值")
    private String newValue;

    @Schema(description = "操作原因")
    private String reason;

    @Schema(description = "创建时间")
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
