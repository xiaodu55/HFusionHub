package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 知识库实体
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("knowledge_base")
@Schema(description = "知识库实体")
public class KnowledgeBase extends BaseEntity {

    /**
     * 知识库ID
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "知识库ID")
    private Long id;

    /**
     * 知识库名称
     */
    @Schema(description = "知识库名称")
    private String name;

    /**
     * 知识库描述
     */
    @Schema(description = "知识库描述")
    private String description;

    /**
     * 创建者ID
     */
    @Schema(description = "创建者ID")
    private Long userId;

    /**
     * 状态：0-正常，1-禁用
     */
    @Schema(description = "状态：0-正常，1-禁用")
    private Integer status;
}
