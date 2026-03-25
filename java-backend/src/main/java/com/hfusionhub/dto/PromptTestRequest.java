package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 提示词测试台请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "提示词测试台请求")
public class PromptTestRequest {

    @NotBlank(message = "模板内容不能为空")
    @Schema(description = "模板正文（系统指令）", requiredMode = Schema.RequiredMode.REQUIRED, example = "请使用简洁、清晰的中文回答")
    @Size(max = 8000, message = "模板内容不能超过8000个字符")
    private String templateContent;

    @NotBlank(message = "测试问题不能为空")
    @Schema(description = "测试问题", requiredMode = Schema.RequiredMode.REQUIRED, example = "请解释什么是RAG")
    @Size(max = 4000, message = "测试问题不能超过4000个字符")
    private String question;

    @Schema(description = "关联知识库ID（可选，用于测试RAG效果）", example = "1")
    private Long knowledgeBaseId;
}
