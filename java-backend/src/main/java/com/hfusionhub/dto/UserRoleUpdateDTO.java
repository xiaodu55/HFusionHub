package com.hfusionhub.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class UserRoleUpdateDTO {

    @NotBlank(message = "角色不能为空")
    private String role;
}
