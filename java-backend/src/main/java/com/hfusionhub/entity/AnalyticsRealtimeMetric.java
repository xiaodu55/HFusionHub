package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 实时聚合指标(Flink 1min 窗口经 JDBC sink upsert;V82)。
 *
 * @author HFusionHub Team
 */
@Data
@TableName("analytics_realtime_metrics")
public class AnalyticsRealtimeMetric {

    @TableId(type = IdType.AUTO)
    private Long id;

    private LocalDateTime windowStart;

    private LocalDateTime windowEnd;

    private Long tenantId;

    private String model;

    private Long requestCount;

    private Long totalTokens;

    private BigDecimal totalCost;

    private Long avgLatencyMs;

    private Long maxLatencyMs;

    private LocalDateTime createdAt;
}
