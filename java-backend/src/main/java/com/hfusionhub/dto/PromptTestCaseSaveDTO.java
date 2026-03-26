package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;
import java.util.Map;

/** 提示词测试用例添加/更新请求 */
@Data
@Schema(description = "提示词测试用例添加/更新请求")
public class PromptTestCaseSaveDTO {

    @NotBlank(message = "测试问题不能为空")
    @Size(max = 4000, message = "测试问题不能超过4000个字符")
    @Schema(description = "固定问题", example = "如何申请退款？")
    private String question;

    @Schema(description = "模板变量值，如 {\"role\":\"客服\",\"topic\":\"退款\"}")
    private Map<String, Object> variables;

    @Schema(description = "期望关键词——AI 回答必须包含每个关键词（不区分大小写），用于自动判定通过")
    private List<String> expectedKeywords;

    @Schema(description = "必须引用的文档 ID——AI 回答的来源必须包含这些文档，用于自动判定通过")
    private List<Long> requiredDocumentIds;

    @Schema(description = "排序号，越大越靠后")
    private Integer sortOrder;
}
