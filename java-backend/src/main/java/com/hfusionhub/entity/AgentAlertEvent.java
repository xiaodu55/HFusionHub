package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.hfusionhub.handler.JsonMapTypeHandler;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * Agent 告警事件记录实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName(value = "agent_alert_event", autoResultMap = true)
@Schema(description = "Agent告警事件")
public class AgentAlertEvent {

    @TableId(type = IdType.AUTO)
    @Schema(description = "事件ID")
    private Long id;

    @Schema(description = "触发规则ID")
    private Long ruleId;

    @Schema(description = "规则名称(冗余)")
    private String ruleName;

    @Schema(description = "相关用户ID")
    private Long userId;

    @Schema(description = "相关知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "严重度")
    private String severity;

    @Schema(description = "指标名")
    private String metricName;

    @Schema(description = "当前指标值")
    private Double currentValue;

    @Schema(description = "触发阈值")
    private Double thresholdValue;

    @Schema(description = "告警消息")
    private String message;

    @TableField(typeHandler = JsonMapTypeHandler.class)
    @Schema(description = "上下文数据")
    private Map<String, Object> context;

    @Schema(description = "是否已解除")
    private Boolean resolved;

    @Schema(description = "解除时间")
    private LocalDateTime resolvedAt;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
