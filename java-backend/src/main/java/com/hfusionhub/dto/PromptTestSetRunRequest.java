package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** 批量运行测试用例集请求 */
@Data
@Schema(description = "批量运行测试用例集请求")
public class PromptTestSetRunRequest {

    @Size(max = 8000, message = "模板内容不能超过8000个字符")
    @Schema(description = "模板内容（作为 system 指令，支持 {{变量}} 替换）。绑定模板时由后端从数据库读取，可省略", example = "你是{{role}}，请用中文回答。")
    private String templateContent;

    @Schema(description = "关联知识库 ID（可选，测试 RAG 效果）")
    private Long knowledgeBaseId;

    @Schema(description = "来源模板 ID（可选，用于记录版本对比）")
    private Long templateId;

    @Schema(description = "来源模板版本号（可选，与 templateId 搭配）")
    private Integer templateVersion;

    @Schema(description = "来源模板名称（可选，展示用快照）")
    private String templateName;
}
