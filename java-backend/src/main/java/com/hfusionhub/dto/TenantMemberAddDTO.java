package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 租户成员添加入参 — 替代裸 Map，避免 userId 缺失/非法时抛 500。
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "添加租户成员请求")
public class TenantMemberAddDTO {

    @NotNull(message = "userId 不能为空")
    @Schema(description = "待添加的用户 ID")
    private Long userId;

    @Schema(description = "角色，默认 member")
    private String role;
}
