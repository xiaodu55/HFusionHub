package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** 提示词测试用例集创建/更新请求 */
@Data
@Schema(description = "提示词测试用例集创建/更新请求")
public class PromptTestSetSaveDTO {

    @NotBlank(message = "用例集名称不能为空")
    @Size(max = 100, message = "用例集名称不能超过100个字符")
    @Schema(description = "用例集名称", example = "客服话术回归")
    private String name;

    @Size(max = 500, message = "用例集描述不能超过500个字符")
    @Schema(description = "用例集描述")
    private String description;
}
