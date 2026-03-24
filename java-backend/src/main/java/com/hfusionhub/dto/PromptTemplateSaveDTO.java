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

    /** 客户端当前持有的版本号，用于并发修改保护。与数据库版本不一致时拒绝覆盖（HTTP 409）。
     *  创建时无需传递；更新/发布/撤回/回滚时必须携带。 */
    private Integer expectedVersion;
}
