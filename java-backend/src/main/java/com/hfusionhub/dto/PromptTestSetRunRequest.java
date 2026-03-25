package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** 批量运行测试用例集请求 */
@Data
@Schema(description = "批量运行测试用例集请求")
public class PromptTestSetRunRequest {

    @NotBlank(message = "模板内容不能为空")
    @Size(max = 8000, message = "模板内容不能超过8000个字符")
    @Schema(description = "模板内容（作为 system 指令，支持 {{变量}} 替换）", example = "你是{{role}}，请用中文回答。")
    private String templateContent;

    @Schema(description = "关联知识库 ID（可选，测试 RAG 效果）")
    private Long knowledgeBaseId;
}
