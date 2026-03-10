package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.util.Map;

/**
 * Agent 单任务/Run 指标详情
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "Agent指标详情")
public class AgentMetricsDTO {

    @Schema(description = "任务ID")
    private Long taskId;

    @Schema(description = "Run ID")
    private Long runId;

    @Schema(description = "Run UUID")
    private String runUuid;

    @Schema(description = "状态")
    private String status;

    @Schema(description = "总耗时(ms)")
    private Long totalDurationMs;

    @Schema(description = "平均每步耗时(ms)")
    private Long avgStepLatencyMs;

    @Schema(description = "最大步耗时(ms)")
    private Long maxStepLatencyMs;

    @Schema(description = "总Token消耗")
    private Long totalTokens;

    @Schema(description = "Prompt Token")
    private Long promptTokens;

    @Schema(description = "Completion Token")
    private Long completionTokens;

    @Schema(description = "工具调用次数")
    private Integer toolCallsCount;

    @Schema(description = "引用来源数")
    private Integer sourcesCount;

    @Schema(description = "步骤数")
    private Integer stepCount;

    @Schema(description = "审批次数")
    private Integer approvalCount;

    @Schema(description = "审批总耗时(ms)")
    private Long avgApprovalDurationMs;

    @Schema(description = "错误码")
    private String errorCode;

    @Schema(description = "错误详情")
    private String errorDetail;

    @Schema(description = "失败的工具名")
    private String failedTool;

    @Schema(description = "使用的模型")
    private String model;

    @Schema(description = "回答风格")
    private String style;

    @Schema(description = "最大工具步数")
    private Integer maxToolSteps;

    @Schema(description = "Token使用详情")
    private Map<String, Object> tokenUsage;
}
