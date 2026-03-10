package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.hfusionhub.handler.JsonListTypeHandler;
import com.hfusionhub.handler.JsonMapTypeHandler;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * Agent 评测执行记录实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName(value = "agent_evaluation_run", autoResultMap = true)
@Schema(description = "Agent评测执行记录")
public class AgentEvaluationRun {

    @TableId(type = IdType.AUTO)
    @Schema(description = "执行记录ID")
    private Long id;

    @Schema(description = "评测集ID")
    private Long datasetId;

    @Schema(description = "执行UUID")
    private String runUuid;

    @Schema(description = "状态: running|completed|failed")
    private String status;

    @Schema(description = "综合得分(0-1)")
    private Double overallScore;

    @TableField(typeHandler = JsonMapTypeHandler.class)
    @Schema(description = "各维度得分")
    private Map<String, Object> dimensionScores;

    @TableField(typeHandler = JsonMapTypeHandler.class)
    @Schema(description = "各用例结果摘要")
    private Map<String, Object> caseResults;

    @TableField(typeHandler = JsonListTypeHandler.class)
    @Schema(description = "未通过用例ID列表")
    private java.util.List<String> failedCaseIds;

    @Schema(description = "错误详情")
    private String errorDetail;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
