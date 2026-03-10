package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.hfusionhub.handler.JsonListTypeHandler;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Agent 离线评测集实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName(value = "agent_evaluation_dataset", autoResultMap = true)
@Schema(description = "Agent离线评测集")
public class AgentEvaluationDataset {

    @TableId(type = IdType.AUTO)
    @Schema(description = "评测集ID")
    private Long id;

    @Schema(description = "评测集名称")
    private String name;

    @Schema(description = "评测集描述")
    private String description;

    @Schema(description = "关联知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "创建者用户ID")
    private Long userId;

    @TableField(typeHandler = JsonListTypeHandler.class)
    @Schema(description = "覆盖的评测维度")
    private List<String> dimensions;

    @Schema(description = "用例数量")
    private Integer caseCount;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
