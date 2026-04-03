package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 角色权限映射实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName("role_permission")
@Schema(description = "角色权限映射")
public class RolePermission {

    @Schema(description = "角色: owner|admin|member|viewer")
    private String role;

    @Schema(description = "权限码: e.g. kb:create")
    private String permission;
}
