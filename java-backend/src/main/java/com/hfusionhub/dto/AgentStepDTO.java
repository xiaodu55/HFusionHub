package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import lombok.Builder;
import lombok.Data;

/**
 * Agent 步骤记录
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "Agent步骤记录")
public class AgentStepDTO {

    @Schema(description = "步骤ID")
    private Long id;

    @Schema(description = "运行ID")
    private Long runId;

    @Schema(description = "步骤序号")
    private Integer sequence;

    @Schema(description = "步骤类型")
    private String stepType;

    @Schema(description = "动作名")
    private String action;

    @Schema(description = "输入摘要")
    private String inputSummary;

    @Schema(description = "输出摘要")
    private String outputSummary;

    @Schema(description = "引用来源")
    private List<Map<String, Object>> sources;

    @Schema(description = "耗时(ms)")
    private Long durationMs;

    @Schema(description = "错误码")
    private String errorCode;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;
}
