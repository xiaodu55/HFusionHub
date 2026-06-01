package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 订阅套餐目录实体（招投标垂直化 · P2）
 *
 * <p>tenantId 可空 = 平台内置套餐（free/pro/enterprise + 行业方案包）；非空 = 租户自定义套餐。
 * 本表为平台目录，加入 {@code MybatisPlusConfig.TENANT_IGNORE_TABLES}，租户查询可见全目录。</p>
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("bid_subscription")
@Schema(description = "订阅套餐目录实体")
public class BidSubscription extends BaseEntity {

    /** 套餐类型 */
    public static final String PLAN_TYPE_TIER = "tier";
    public static final String PLAN_TYPE_INDUSTRY = "industry";

    /** 状态 */
    public static final String STATUS_ACTIVE = "active";
    public static final String STATUS_ARCHIVED = "archived";

    /** 模块开关键（module_flags JSON） */
    public static final String MODULE_DRAFT = "draft";
    public static final String MODULE_CHECK = "check";
    public static final String MODULE_DOCX = "docx";
    public static final String MODULE_OPENAPI = "openapi";

    /** 全部可售模块（P2-2 平台开关 + 前端套餐状态枚举） */
    public static final java.util.Set<String> MODULE_KEYS =
            java.util.Set.of(MODULE_DRAFT, MODULE_CHECK, MODULE_DOCX, MODULE_OPENAPI);

    @TableId(type = IdType.AUTO)
    @Schema(description = "套餐ID")
    private Long id;

    @Schema(description = "租户ID；NULL=平台内置套餐")
    private Long tenantId;

    @Schema(description = "套餐代码 free|pro|enterprise|industry_construction|industry_it")
    private String planCode;

    @Schema(description = "套餐名称")
    private String planName;

    @Schema(description = "套餐类型：tier|industry")
    private String planType;

    @Schema(description = "月度价格（分）")
    private Long priceCents;

    @Schema(description = "最大投标项目数")
    private Integer maxProjects;

    @Schema(description = "最大坐席数（tenant_member 数）")
    private Integer maxSeats;

    @Schema(description = "标书撰写月度字符额度")
    private Long charQuota;

    @Schema(description = "模块开关 JSON：{\"draft\":true,\"check\":true,\"docx\":false,\"openapi\":false}")
    private String moduleFlags;

    @Schema(description = "状态：active|archived")
    private String status;

    @Schema(description = "创建人")
    private Long createdBy;
}
