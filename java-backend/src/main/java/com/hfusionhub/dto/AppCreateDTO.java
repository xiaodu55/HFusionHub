package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 创建应用请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "创建应用请求")
public class AppCreateDTO {

    @NotBlank(message = "应用名称不能为空")
    @Size(max = 200, message = "应用名称长度不能超过200")
    @Schema(description = "应用名称")
    private String name;

    @Size(max = 500, message = "应用描述长度不能超过500")
    @Schema(description = "应用描述")
    private String description;

    @Schema(description = "绑定知识库ID（空=通用对话）")
    private Long knowledgeBaseId;

    @Schema(description = "可选提示词模板ID")
    private Long promptTemplateId;

    @Size(max = 200, message = "模型名称长度不能超过200")
    @Schema(description = "模型覆盖（空=系统默认）")
    private String model;

    @Size(max = 20, message = "回答风格长度不能超过20")
    @Schema(description = "concise | detailed | report，默认 detailed")
    private String style;
}
