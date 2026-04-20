package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 应用信息（返回给前端）
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "应用信息")
public class AppInfoDTO {

    @Schema(description = "应用ID")
    private Long id;

    @Schema(description = "应用名称")
    private String name;

    @Schema(description = "应用描述")
    private String description;

    @Schema(description = "绑定知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "绑定知识库名称")
    private String knowledgeBaseName;

    @Schema(description = "提示词模板ID")
    private Long promptTemplateId;

    @Schema(description = "模型覆盖")
    private String model;

    @Schema(description = "回答风格")
    private String style;

    @Schema(description = "0 草稿, 1 已发布, 2 已停用")
    private Integer status;

    @Schema(description = "有效 API Key 数量")
    private Long apiKeyCount;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
