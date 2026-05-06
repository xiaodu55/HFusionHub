package com.hfusionhub.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

/**
 * 主题偏好更新请求
 *
 * @author HFusionHub Team
 */
@Data
public class ThemePreferenceUpdateDTO {

    @NotBlank(message = "主题偏好不能为空")
    @Pattern(regexp = "^(light|dark|system)$", message = "主题偏好必须是 light、dark 或 system")
    private String themePreference;
}
