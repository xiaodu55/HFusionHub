package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.hfusionhub.handler.JsonListTypeHandler;
import com.hfusionhub.handler.JsonMapTypeHandler;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * Agent 评测用例实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName(value = "agent_evaluation_case", autoResultMap = true)
@Schema(description = "Agent评测用例")
public class AgentEvaluationCase {

    @TableId(type = IdType.AUTO)
    @Schema(description = "用例ID")
    private Long id;

    @Schema(description = "所属评测集ID")
    private Long datasetId;

    @Schema(description = "测试查询")
    private String query;

    @Schema(description = "期望答案(ground truth)")
    private String expectedAnswer;

    @TableField(typeHandler = JsonListTypeHandler.class)
    @Schema(description = "期望引用的文档ID列表")
    private List<String> expectedSources;

    @TableField(typeHandler = JsonMapTypeHandler.class)
    @Schema(description = "越权测试配置")
    private Map<String, Object> privilegeTest;

    @TableField(typeHandler = JsonMapTypeHandler.class)
    @Schema(description = "用例元数据")
    private Map<String, Object> metadata;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
