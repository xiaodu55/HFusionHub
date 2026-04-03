package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 租户成员实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName("tenant_member")
@Schema(description = "租户成员实体")
public class TenantMember {

    @TableId(type = IdType.AUTO)
    @Schema(description = "成员ID")
    private Long id;

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "角色: owner|admin|member|viewer")
    private String role;

    @Schema(description = "加入时间")
    private LocalDateTime joinedAt;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;

    @TableLogic
    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "删除标记")
    private Integer deleted;
}
