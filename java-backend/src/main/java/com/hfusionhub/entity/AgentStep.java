package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.hfusionhub.handler.JsonTypeHandler;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * Agent 步骤记录实体 — 每次工具调用/检索/生成一条记录
 *
 * @author HFusionHub Team
 */
@Data
@TableName("agent_step")
@Schema(description = "Agent步骤记录")
public class AgentStep {

    /**
     * 步骤ID
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "步骤ID")
    private Long id;

    /**
     * 关联运行ID
     */
    @Schema(description = "运行ID")
    private Long runId;

    /**
     * 步骤序号（从1开始）
     */
    @Schema(description = "步骤序号")
    private Integer sequence;

    /**
     * 步骤类型：intent_classification|retrieval|tool_call|model_generation|reflection|grounding_check
     */
    @Schema(description = "步骤类型")
    private String stepType;

    /**
     * 工具名或阶段名
     */
    @Schema(description = "动作名")
    private String action;

    /**
     * 输入摘要（截断）
     */
    @Schema(description = "输入摘要")
    private String inputSummary;

    /**
     * 输出摘要（截断）
     */
    @Schema(description = "输出摘要")
    private String outputSummary;

    /**
     * 引用来源
     */
    @TableField(typeHandler = JsonTypeHandler.class)
    @Schema(description = "引用来源")
    private List<Map<String, Object>> sources;

    /**
     * 此步耗时（毫秒）
     */
    @Schema(description = "耗时(ms)")
    private Long durationMs;

    /**
     * 错误码
     */
    @Schema(description = "错误码")
    private String errorCode;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
