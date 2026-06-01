package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 租户套餐绑定实体（招投标垂直化 · P2）
 *
 * <p>多套餐支持：租户可同时绑定基础档位（tier）+ 多个行业方案包（industry），按授权售卖。
 * 本表为租户私有（tenant_id NOT NULL），由租户行拦截器自动隔离。</p>
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("tenant_plan_binding")
@Schema(description = "租户套餐绑定实体")
public class TenantPlanBinding extends BaseEntity {

    /** 状态 */
    public static final String STATUS_ACTIVE = "active";
    public static final String STATUS_EXPIRED = "expired";
    public static final String STATUS_CANCELED = "canceled";

    @TableId(type = IdType.AUTO)
    @Schema(description = "绑定ID")
    private Long id;

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "套餐ID（FK bid_subscription.id）")
    private Long subscriptionId;

    @Schema(description = "生效时间")
    private LocalDateTime startAt;

    @Schema(description = "到期时间；NULL=长期有效")
    private LocalDateTime endAt;

    @Schema(description = "状态：active|expired|canceled")
    private String status;

    @Schema(description = "操作人")
    private Long createdBy;
}
