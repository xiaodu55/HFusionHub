package com.hfusionhub.service;

import com.hfusionhub.entity.AdsCostDaily;
import com.hfusionhub.entity.AdsEvalQuality;
import com.hfusionhub.entity.AdsModelShare;
import com.hfusionhub.entity.AdsToolSuccess;
import com.hfusionhub.entity.AnalyticsRealtimeMetric;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * 运营分析服务(HFusionData Analytics 应用层)。
 *
 * <p>数据源是 Spark ADS 的 MySQL 镜像(V82)与 Flink 实时指标 ——
 * 业务侧零 Hadoop 依赖。租户隔离在服务端强制:普通用户只能看本租户,
 * 平台管理员(crossTenant)可传 tenantId 查指定租户/-1 平台全局/null 全部。</p>
 *
 * @author HFusionHub Team
 */
public interface AnalyticsService {

    /** 概览:近 N 天累计调用/token/成本 + 最近实时窗口速率 */
    Map<String, Object> overview(int days);

    /** 每日成本趋势(含平台全局 -1 行;按租户隔离) */
    List<AdsCostDaily> costDaily(int days, Long tenantId);

    /** 模型成本占比(指定日,默认 T-1) */
    List<AdsModelShare> modelShare(LocalDate date, Long tenantId);

    /** Agent 步骤成功率(近 N 天) */
    List<AdsToolSuccess> toolSuccess(int days, Long tenantId);

    /** 检索/评测质量趋势(近 N 天) */
    List<AdsEvalQuality> evalQuality(int days, Long tenantId);

    /** 实时指标(近 N 分钟,1min 窗口) */
    List<AnalyticsRealtimeMetric> realtime(int minutes, Long tenantId);
}
