package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.entity.AgentAlertEvent;
import com.hfusionhub.entity.AgentAlertRule;

import java.util.List;

/**
 * Agent 告警规则管理与告警检查服务
 *
 * @author HFusionHub Team
 */
public interface AgentAlertService {

    // ── 告警规则 CRUD ──

    AgentAlertRule createRule(AgentAlertRule rule);
    AgentAlertRule updateRule(AgentAlertRule rule);
    void deleteRule(Long ruleId);
    AgentAlertRule getRule(Long ruleId);
    List<AgentAlertRule> listRules(Long userId);

    // ── 告警事件查询 ──

    PageResult<AgentAlertEvent> listAlertEvents(Long userId, int page, int pageSize);
    List<AgentAlertEvent> listUnresolvedAlerts(Long userId);
    void resolveAlert(Long alertId);

    // ── 告警检查 ──

    /**
     * 对指定用户执行所有已启用规则的告警检查。
     * 返回新触发的告警事件列表。
     */
    List<AgentAlertEvent> checkAlerts(Long userId);

    /**
     * 对所有用户执行告警检查（定时任务调用）。
     */
    List<AgentAlertEvent> checkAllActiveAlerts();
}
