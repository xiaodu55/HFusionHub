package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * Agent 运行记录详情（含所有 Step）
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "Agent运行记录")
public class AgentRunDTO {

    @Schema(description = "运行ID")
    private Long id;

    @Schema(description = "任务ID")
    private Long taskId;

    @Schema(description = "运行UUID")
    private String runUuid;

    @Schema(description = "尝试次数")
    private Integer attemptNumber;

    @Schema(description = "运行状态")
    private String status;

    @Schema(description = "模型名称")
    private String model;

    @Schema(description = "回答风格")
    private String style;

    @Schema(description = "最大工具步数")
    private Integer maxToolSteps;

    @Schema(description = "Token使用统计")
    private Map<String, Object> tokenUsage;

    @Schema(description = "工具调用次数")
    private Integer toolCallsCount;

    @Schema(description = "错误码")
    private String errorCode;

    @Schema(description = "错误详情")
    private String errorDetail;

    @Schema(description = "失败工具名")
    private String failedTool;

    @Schema(description = "开始时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime startedAt;

    @Schema(description = "完成时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime completedAt;

    @Schema(description = "耗时(ms)")
    private Long durationMs;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;

    @Schema(description = "该运行的所有步骤")
    private List<AgentStepDTO> steps;
}
