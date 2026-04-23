package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 租户配额覆盖
 *
 * <p>某租户对某计量项的日限额覆盖值。不存在时回落 plan_tier 默认值
 * （见 application.yml {@code hfusionhub.quota.defaults}）。</p>
 *
 * @author HFusionHub Team
 */
@Data
@TableName("tenant_quota")
@Schema(description = "租户配额覆盖")
public class TenantQuota {

    @TableId(type = IdType.AUTO)
    @Schema(description = "ID")
    private Long id;

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "计量项")
    private String meter;

    @Schema(description = "日限额覆盖值")
    private Long dailyLimit;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
