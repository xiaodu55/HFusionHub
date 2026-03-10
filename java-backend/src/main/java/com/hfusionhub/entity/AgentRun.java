package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.hfusionhub.handler.JsonTypeHandler;
import com.hfusionhub.handler.JsonMapTypeHandler;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * Agent 运行记录实体 — 每次执行尝试一条记录
 *
 * @author HFusionHub Team
 */
@Data
@TableName("agent_run")
@Schema(description = "Agent运行记录")
public class AgentRun {

    /**
     * 运行ID
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "运行ID")
    private Long id;

    /**
     * 关联任务ID
     */
    @Schema(description = "任务ID")
    private Long taskId;

    /**
     * UUID，对应 Python 的 agent_run_id
     */
    @Schema(description = "运行UUID")
    private String runUuid;

    /**
     * 第N次尝试（1-based）
     */
    @Schema(description = "尝试次数")
    private Integer attemptNumber;

    /**
     * 状态：pending|running|succeeded|failed|cancelled|timed_out
     */
    @Schema(description = "运行状态")
    private String status;

    /**
     * 使用的模型
     */
    @Schema(description = "模型名称")
    private String model;

    /**
     * 回答风格
     */
    @Schema(description = "回答风格")
    private String style;

    /**
     * 最大工具步数
     */
    @Schema(description = "最大工具步数")
    private Integer maxToolSteps;

    /**
     * Token 使用统计
     */
    @TableField(typeHandler = JsonMapTypeHandler.class)
    @Schema(description = "token统计")
    private Map<String, Object> tokenUsage;

    /**
     * 工具调用次数
     */
    @Schema(description = "工具调用次数")
    private Integer toolCallsCount;

    /**
     * 错误码
     */
    @Schema(description = "错误码")
    private String errorCode;

    /**
     * 错误详情
     */
    @Schema(description = "错误详情")
    private String errorDetail;

    /**
     * 失败的工具名
     */
    @Schema(description = "失败工具名")
    private String failedTool;

    /**
     * 开始执行时间
     */
    @Schema(description = "开始时间")
    private LocalDateTime startedAt;

    /**
     * 完成时间
     */
    @Schema(description = "完成时间")
    private LocalDateTime completedAt;

    /**
     * 执行耗时（毫秒）
     */
    @Schema(description = "耗时(ms)")
    private Long durationMs;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
