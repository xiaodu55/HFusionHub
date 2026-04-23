package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * Agent 告警规则配置实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName("agent_alert_rule")
@Schema(description = "Agent告警规则")
public class AgentAlertRule {

    @TableId(type = IdType.AUTO)
    @Schema(description = "规则ID")
    private Long id;

    @Schema(description = "规则名称")
    private String name;

    @Schema(description = "规则描述")
    private String description;

    @Schema(description = "用户ID(NULL=全局规则)")
    private Long userId;

    @Schema(description = "监控指标名")
    private String metricName;

    @Schema(description = "比较符: gt|gte|lt|lte|eq")
    private String comparisonOperator;

    @Schema(description = "阈值")
    private Double thresholdValue;

    @Schema(description = "评估窗口(分钟)")
    private Integer windowMinutes;

    @Schema(description = "严重度: critical|warning|info")
    private String severity;

    @Schema(description = "冷却时间(分钟)")
    private Integer cooldownMinutes;

    @Schema(description = "是否启用")
    private Boolean enabled;

    @Schema(description = "上次触发时间")
    private LocalDateTime lastTriggeredAt;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
