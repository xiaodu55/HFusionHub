package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 检索/评测质量趋势(Spark ADS 镜像)。
 *
 * @author HFusionHub Team
 */
@Data
@TableName("ads_eval_quality")
public class AdsEvalQuality {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long tenantId;

    private LocalDate statDate;

    private Long evalCount;

    private Double avgHitRatio;

    private Long avgTtftMs;

    private Long avgLatencyMs;

    private Double failureRate;

    private LocalDateTime createdAt;
}
