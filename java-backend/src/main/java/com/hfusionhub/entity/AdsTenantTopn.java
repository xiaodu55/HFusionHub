package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 租户用量 TopN(平台管理员视图,Spark ADS 镜像)。
 *
 * @author HFusionHub Team
 */
@Data
@TableName("ads_tenant_topn")
public class AdsTenantTopn {

    @TableId(type = IdType.AUTO)
    private Long id;

    private LocalDate statDate;

    private Integer rankNo;

    private Long tenantId;

    private Long callCount;

    private Long totalTokens;

    private BigDecimal costUsd;

    private LocalDateTime createdAt;
}
