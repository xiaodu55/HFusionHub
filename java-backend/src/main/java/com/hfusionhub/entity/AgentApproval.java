package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * Agent 审批记录实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName("agent_approval")
@Schema(description = "Agent审批记录")
public class AgentApproval {

    @TableId(type = IdType.AUTO)
    @Schema(description = "审批记录ID")
    private Long id;

    @Schema(description = "审批UUID")
    private String approvalId;

    @Schema(description = "关联任务ID")
    private Long taskId;

    @Schema(description = "关联运行ID")
    private Long runId;

    @Schema(description = "审批目标用户ID")
    private Long userId;

    @Schema(description = "审批目标用户角色")
    private String userRole;

    @Schema(description = "分布式追踪 ID")
    private String traceId;

    @Schema(description = "工具名称")
    private String toolName;

    @Schema(description = "工具参数SHA-256摘要")
    private String toolInputHash;

    @Schema(description = "一次性执行令牌")
    private String executionToken;

    @Schema(description = "执行令牌状态: none|issued|consumed|revoked")
    private String executionTokenStatus;

    @Schema(description = "令牌签发时间")
    private java.time.LocalDateTime executionTokenIssuedAt;

    @Schema(description = "令牌消耗时间")
    private java.time.LocalDateTime executionTokenConsumedAt;

    /** Exact JSON parameters approved by the user. Kept separately from the redacted summary. */
    @TableField(value = "tool_input")
    private String toolInput;

    @Schema(description = "参数摘要(脱敏)")
    private String argumentsSummary;

    @Schema(description = "审批状态: pending|approved|denied|expired")
    private String status;

    @Schema(description = "审批人用户ID")
    private Long decidedBy;

    @Schema(description = "审批决定时间")
    private LocalDateTime decidedAt;

    @Schema(description = "审批决定原因")
    private String reason;

    @Schema(description = "过期时间")
    private LocalDateTime expiresAt;

    @Schema(description = "创建时间")
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
