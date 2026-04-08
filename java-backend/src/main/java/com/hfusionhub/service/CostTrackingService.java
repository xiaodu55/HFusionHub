package com.hfusionhub.service;

import com.hfusionhub.dto.CostSummaryDTO;
import com.hfusionhub.dto.DailyCostDTO;
import com.hfusionhub.dto.TenantCostSummaryDTO;
import com.hfusionhub.entity.ModelUsageRecord;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 模型调用成本追踪服务
 *
 * @author HFusionHub Team
 */
public interface CostTrackingService {

    /**
     * 记录一次模型调用成本
     *
     * @param record 成本记录（追加式插入）
     */
    void record(ModelUsageRecord record);

    /**
     * 获取某用户最近 N 天的每日成本明细（图表数据）
     *
     * @param userId 用户ID
     * @param days   最近天数（1-90，默认 30）
     * @return 每日成本列表（按日期升序）
     */
    List<DailyCostDTO> getUserDailyCost(Long userId, int days);

    /**
     * 获取租户在时间范围内的成本汇总（总额 + 按模型分组）
     *
     * @param tenantId 租户ID
     * @param start    起始时间（可为 null，默认最近 30 天）
     * @param end      结束时间（可为 null，默认当前时间）
     * @return 租户成本汇总
     */
    TenantCostSummaryDTO getTenantCostSummary(Long tenantId, LocalDateTime start, LocalDateTime end);

    /**
     * 获取当前用户成本汇总（近 30 天总额 + 本月预估 + 按模型分组）
     *
     * @param userId 用户ID
     * @return 成本汇总
     */
    CostSummaryDTO getCostSummary(Long userId);

    /**
     * 预估用户本月最终成本（按本月已发生成本 / 已过天数 * 当月天数外推）
     *
     * @param userId 用户ID
     * @return 预估成本（美元）
     */
    double getCurrentMonthEstimate(Long userId);
}
