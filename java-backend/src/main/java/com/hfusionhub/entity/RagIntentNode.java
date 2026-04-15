package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
@TableName("rag_intent_node")
@Schema(description = "RAG intent tree node")
public class RagIntentNode extends BaseEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private Long tenantId;

    private Long parentId;

    private String intentCode;

    private String name;

    private String description;

    private String level;

    private String kind;

    private Long knowledgeBaseId;

    private Long mcpToolId;

    private Integer topK;

    private String routeConfig;

    private Integer enabled;

    private Integer sortOrder;
}
