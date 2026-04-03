package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 租户实体
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("tenant")
@Schema(description = "租户实体")
public class Tenant extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "租户ID")
    private Long id;

    @Schema(description = "租户名称")
    private String name;

    @Schema(description = "唯一标识符")
    private String slug;

    @Schema(description = "计划层级: free|pro|enterprise")
    private String planTier;

    @Schema(description = "状态: active|suspended|deleted")
    private String status;

    @Schema(description = "创建者（平台管理员）ID")
    private Long createdBy;
}
