package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 每日成本趋势(Spark ADS 镜像;tenant_id=-1 为平台全局口径)。
 *
 * @author HFusionHub Team
 */
@Data
@TableName("ads_cost_daily")
public class AdsCostDaily {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long tenantId;

    private LocalDate statDate;

    private Long callCount;

    private Long totalTokens;

    private BigDecimal costUsd;

    private BigDecimal estMonthCost;

    private LocalDateTime createdAt;
}
