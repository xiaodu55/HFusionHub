package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 模型成本占比(Spark ADS 镜像)。
 *
 * @author HFusionHub Team
 */
@Data
@TableName("ads_model_share")
public class AdsModelShare {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long tenantId;

    private String model;

    private LocalDate statDate;

    private Long callCount;

    private BigDecimal costUsd;

    private Double costShare;

    private LocalDateTime createdAt;
}
