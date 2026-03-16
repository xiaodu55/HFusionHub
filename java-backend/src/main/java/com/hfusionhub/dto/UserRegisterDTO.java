package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 用户注册请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "用户注册请求")
public class UserRegisterDTO {

    @NotBlank(message = "用户名不能为空")
    @Size(min = 3, max = 50, message = "用户名长度必须在3-50之间")
    @Pattern(regexp = "^[\\p{L}\\p{N}_-]+$", message = "用户名只能包含文字、数字、下划线或短横线")
    @Schema(description = "用户名", requiredMode = Schema.RequiredMode.REQUIRED, example = "testuser")
    private String username;

    @NotBlank(message = "密码不能为空")
    @Size(min = 8, max = 72, message = "密码长度必须在8-72之间")
    @Pattern(regexp = "^(?=.*[A-Za-z])(?=.*\\d).+$", message = "密码必须同时包含字母和数字")
    @Schema(description = "密码", requiredMode = Schema.RequiredMode.REQUIRED, example = "123456")
    private String password;

    @Size(max = 50, message = "昵称长度不能超过50")
    @Schema(description = "昵称", example = "测试用户")
    private String nickname;

    @Email(message = "邮箱格式不正确")
    @Size(max = 100, message = "邮箱长度不能超过100")
    @Schema(description = "邮箱", example = "test@example.com")
    private String email;

    @Pattern(regexp = "^\\+?[1-9]\\d{6,14}$", message = "手机号格式不正确")
    @Schema(description = "手机号（E.164 格式，可选）", example = "13800138000")
    private String phone;
}
