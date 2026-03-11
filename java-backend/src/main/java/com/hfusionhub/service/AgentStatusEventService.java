package com.hfusionhub.service;

import com.hfusionhub.dto.AgentStatusEventDTO;

import java.util.List;
import java.util.Map;

/**
 * Agent 状态事件服务 — SSE 推送数据源 + 审计日志
 *
 * @author HFusionHub Team
 */
public interface AgentStatusEventService {

    /**
     * 记录状态事件（独立短事务，不参与业务事务）
     *
     * @param taskId    任务ID
     * @param runId     运行ID（可能为空）
     * @param eventType 事件类型
     * @param status    事件发生时任务状态
     * @param payload   附加载荷
     */
    void record(Long taskId, Long runId, String eventType, String status,
                Map<String, Object> payload);

    /**
     * 按任务ID查询事件（支持断点续传 sinceId）
     *
     * @param taskId  任务ID
     * @param sinceId 从该ID之后开始查（不含）
     * @param limit   数量限制
     */
    List<AgentStatusEventDTO> listEvents(Long taskId, Long sinceId, int limit);

    /**
     * 按任务ID查询最新一条事件
     */
    AgentStatusEventDTO getLatestEvent(Long taskId);

    /**
     * 清理过期事件（定时任务调用）
     */
    int cleanupEvents();
}
