package com.hfusionhub.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class PromptTemplateSaveDTO {
    @NotBlank(message = "模板名称不能为空")
    @Size(max = 100, message = "模板名称不能超过 100 个字符")
    private String name;

    @Size(max = 500, message = "模板说明不能超过 500 个字符")
    private String description;

    @NotBlank(message = "系统指令不能为空")
    @Size(max = 8000, message = "系统指令不能超过 8000 个字符")
    private String content;
}
