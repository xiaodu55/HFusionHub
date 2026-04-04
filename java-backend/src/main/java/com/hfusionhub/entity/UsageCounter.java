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
 * 每日用量计数器
 *
 * <p>每个 (tenant, meter, day) 一行。reserve / settle / release 全部通过条件 UPDATE
 * 原子增减，避免应用层并发竞态。</p>
 *
 * @author HFusionHub Team
 */
@Data
@TableName("usage_counter")
@Schema(description = "每日用量计数器")
public class UsageCounter {

    @TableId(type = IdType.AUTO)
    @Schema(description = "ID")
    private Long id;

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "计量项")
    private String meter;

    @Schema(description = "UTC 日窗口 YYYY-MM-DD")
    private String windowKey;

    @Schema(description = "当日已预占未结算量")
    private Long reserved;

    @Schema(description = "当日已结算（实际消耗）量")
    private Long committed;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
