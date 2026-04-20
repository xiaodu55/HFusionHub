package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 对外发布的应用（Agent）实体
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("app")
@Schema(description = "对外发布的应用")
public class App extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "应用ID")
    private Long id;

    @Schema(description = "应用名称")
    private String name;

    @Schema(description = "应用描述")
    private String description;

    @Schema(description = "所有者（sys_user.id）")
    private Long userId;

    @Schema(description = "租户")
    private Long tenantId;

    @Schema(description = "绑定知识库（空=通用对话）")
    private Long knowledgeBaseId;

    @Schema(description = "可选提示词模板")
    private Long promptTemplateId;

    @Schema(description = "模型覆盖（空=系统默认）")
    private String model;

    @Schema(description = "concise | detailed | report")
    private String style;

    @Schema(description = "0 草稿, 1 已发布, 2 已停用")
    private Integer status;
}
