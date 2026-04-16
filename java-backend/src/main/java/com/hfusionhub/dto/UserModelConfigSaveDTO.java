package com.hfusionhub.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class UserModelConfigSaveDTO {

    @NotBlank(message = "请选择供应商类型")
    @Pattern(regexp = "^(openai_compatible|ollama)$", message = "仅支持 OpenAI 兼容接口或 Ollama")
    private String providerType;

    @NotBlank(message = "供应商名称不能为空")
    @Size(max = 100, message = "供应商名称不能超过100个字符")
    private String providerName;

    @NotBlank(message = "Base URL 不能为空")
    @Size(max = 500, message = "Base URL 不能超过500个字符")
    private String baseUrl;

    @NotBlank(message = "模型名称不能为空")
    @Size(max = 160, message = "模型名称不能超过160个字符")
    private String modelName;

    @Size(max = 1000, message = "API Key 长度不能超过1000个字符")
    private String apiKey;

    private Boolean enabled = true;
}

