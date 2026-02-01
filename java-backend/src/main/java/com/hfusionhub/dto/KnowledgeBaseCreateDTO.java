package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 知识库创建请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "知识库创建请求")
public class KnowledgeBaseCreateDTO {

    @NotBlank(message = "知识库名称不能为空")
    @Size(min = 1, max = 100, message = "知识库名称长度必须在1-100之间")
    @Schema(description = "知识库名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "我的知识库")
    private String name;

    @Size(max = 500, message = "描述长度不能超过500")
    @Schema(description = "知识库描述", example = "这是一个测试知识库")
    private String description;
}
