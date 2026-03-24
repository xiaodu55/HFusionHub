package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 对话实体
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("conversation")
@Schema(description = "对话实体")
public class Conversation extends BaseEntity {

    /**
     * 对话ID
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "对话ID")
    private Long id;

    /**
     * 关联知识库ID
     */
    @Schema(description = "关联知识库ID")
    private Long knowledgeBaseId;

    /** Published prompt template selected for this conversation, if any. */
    private Long promptTemplateId;

    /**
     * 用户ID
     */
    @Schema(description = "用户ID")
    private Long userId;

    /**
     * 对话标题
     */
    @Schema(description = "对话标题")
    private String title;
}
