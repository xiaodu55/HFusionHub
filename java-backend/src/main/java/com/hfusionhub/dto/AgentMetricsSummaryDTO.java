package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * Agent Run 指标列表项（摘要视图）
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "Agent Run指标摘要")
public class AgentMetricsSummaryDTO {

    @Schema(description = "Run ID")
    private Long runId;

    @Schema(description = "Run UUID")
    private String runUuid;

    @Schema(description = "任务ID")
    private Long taskId;

    @Schema(description = "知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "用户查询(截断)")
    private String querySummary;

    @Schema(description = "状态")
    private String status;

    @Schema(description = "模型")
    private String model;

    @Schema(description = "耗时(ms)")
    private Long durationMs;

    @Schema(description = "Token总数")
    private Long totalTokens;

    @Schema(description = "工具调用次数")
    private Integer toolCallsCount;

    @Schema(description = "引用来源数")
    private Integer sourcesCount;

    @Schema(description = "错误码")
    private String errorCode;

    @Schema(description = "开始时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime startedAt;

    @Schema(description = "完成时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime completedAt;
}
