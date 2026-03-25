package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

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

    @Schema(description = "排序号，越大越靠后")
    private Integer sortOrder;
}
