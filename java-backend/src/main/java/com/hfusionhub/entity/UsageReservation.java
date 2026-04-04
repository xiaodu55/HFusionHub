package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 用量预占状态机（每 (tenant_id, meter, request_id) 一行）
 *
 * <p>状态只能从 RESERVED 原子转换到 COMMITTED 或 RELEASED 之一，杜绝
 * COMMIT 后再 RELEASE / RELEASE 后再 COMMIT 造成的 reserved 扣负。</p>
 *
 * @author HFusionHub Team
 */
@Data
@TableName("usage_reservation")
@Schema(description = "用量预占状态机")
public class UsageReservation {

    public static final String STATE_RESERVED = "RESERVED";
    public static final String STATE_COMMITTED = "COMMITTED";
    public static final String STATE_RELEASED = "RELEASED";

    @TableId(type = IdType.AUTO)
    @Schema(description = "ID")
    private Long id;

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "计量项")
    private String meter;

    @Schema(description = "业务幂等键")
    private String requestId;

    @Schema(description = "预占所在 UTC 日窗口 YYYY-MM-DD")
    private String windowKey;

    @Schema(description = "预占上界")
    private Long reservedAmount;

    @Schema(description = "实际结算量")
    private Long actualAmount;

    @Schema(description = "状态: RESERVED|COMMITTED|RELEASED")
    private String state;

    @Schema(description = "引用类型")
    private String refType;

    @Schema(description = "引用ID")
    private String refId;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
