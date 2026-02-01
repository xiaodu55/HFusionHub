package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 用户更新请求
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "用户更新请求")
public class UserUpdateDTO {

    @Size(min = 2, max = 50, message = "昵称长度必须在2-50之间")
    @Schema(description = "昵称", example = "新昵称")
    private String nickname;

    @Email(message = "邮箱格式不正确")
    @Schema(description = "邮箱", example = "newemail@example.com")
    private String email;

    @Schema(description = "手机号", example = "13900139000")
    private String phone;

    @Schema(description = "头像URL", example = "https://example.com/avatar.jpg")
    private String avatar;
}
