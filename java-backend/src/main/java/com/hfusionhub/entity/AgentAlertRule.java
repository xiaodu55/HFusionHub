package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
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

    @NotBlank(message = "规则名称不能为空")
    @Schema(description = "规则名称")
    private String name;

    @Schema(description = "规则描述")
    private String description;

    @Schema(description = "用户ID(NULL=全局规则)")
    private Long userId;

    @NotBlank(message = "监控指标名不能为空")
    @Schema(description = "监控指标名")
    private String metricName;

    @NotBlank(message = "比较符不能为空")
    @Schema(description = "比较符: gt|gte|lt|lte|eq")
    private String comparisonOperator;

    @NotNull(message = "阈值不能为空")
    @Schema(description = "阈值")
    private Double thresholdValue;

    @NotNull(message = "评估窗口不能为空")
    @Schema(description = "评估窗口(分钟)")
    private Integer windowMinutes;

    @NotBlank(message = "严重度不能为空")
    @Schema(description = "严重度: critical|warning|info")
    private String severity;

    @NotNull(message = "冷却时间不能为空")
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
