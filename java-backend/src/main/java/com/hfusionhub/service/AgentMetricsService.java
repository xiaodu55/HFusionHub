package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.AgentAggregatedStatsDTO;
import com.hfusionhub.dto.AgentMetricsDTO;
import com.hfusionhub.dto.AgentMetricsSummaryDTO;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * Agent 指标聚合与查询服务
 *
 * @author HFusionHub Team
 */
public interface AgentMetricsService {

    /**
     * 获取单个任务的指标（含其所有 Run 的聚合）
     */
    AgentMetricsDTO getTaskMetrics(Long taskId);

    /**
     * 获取单个 Run 的指标
     */
    AgentMetricsDTO getRunMetrics(Long runId);

    /**
     * 获取 Run 指标列表（可分页、可筛选）
     */
    PageResult<AgentMetricsSummaryDTO> listRunMetrics(
            Long userId, Long kbId, String status,
            LocalDateTime start, LocalDateTime end,
            int page, int pageSize);

    /**
     * 聚合统计（按用户、知识库、时间范围聚合）
     */
    AgentAggregatedStatsDTO getAggregatedStats(
            Long userId, Long kbId, int days);

    /**
     * Dashboard 概览（当前用户的今日+近7天统计）
     */
    Map<String, Object> getDashboardStats(Long userId);
}
