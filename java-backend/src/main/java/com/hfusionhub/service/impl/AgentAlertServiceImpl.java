package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.AgentAlertEvent;
import com.hfusionhub.entity.AgentAlertRule;
import com.hfusionhub.entity.AgentApproval;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentStep;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.mapper.AgentAlertEventMapper;
import com.hfusionhub.mapper.AgentAlertRuleMapper;
import com.hfusionhub.mapper.AgentApprovalMapper;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.service.AgentAlertService;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Agent 告警服务实现
 *
 * 实现了 4 种预置告警规则的检查逻辑：
 * - citation_miss_rate: 无 sources 的 completed Run 占比
 * - tool_failure_rate: tool_error 终态占比
 * - running_timeout: 异常 running 超时 (>120s)
 * - approval_timeout: 审批 pending 超时 (>4min)
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentAlertServiceImpl implements AgentAlertService {

    private final AgentAlertRuleMapper ruleMapper;
    private final AgentAlertEventMapper eventMapper;
    private final AgentRunMapper runMapper;
    private final AgentStepMapper stepMapper;
    private final AgentTaskMapper taskMapper;
    private final AgentApprovalMapper approvalMapper;

    // ================================================================
    // 告警规则 CRUD
    // ================================================================

    @Override
    @Transactional
    public AgentAlertRule createRule(Long userId, AgentAlertRule rule) {
        if (userId == null) throw new BusinessException("invalid user");
        rule.setUserId(userId);
        rule.setCreatedAt(LocalDateTime.now());
        rule.setUpdatedAt(LocalDateTime.now());
        rule.setEnabled(rule.getEnabled() != null ? rule.getEnabled() : true);
        rule.setCooldownMinutes(rule.getCooldownMinutes() != null ? rule.getCooldownMinutes() : 60);
        ruleMapper.insert(rule);
        log.info("Created alert rule: id={} name={} metric={}", rule.getId(), rule.getName(), rule.getMetricName());
        return rule;
    }

    @Override
    @Transactional
    public AgentAlertRule updateRule(Long userId, AgentAlertRule rule) {
        AgentAlertRule existing = ruleMapper.selectById(rule.getId());
        requireOwned(userId, existing);
        rule.setUserId(userId);
        if (existing == null) throw new BusinessException("告警规则不存在: " + rule.getId());
        rule.setUpdatedAt(LocalDateTime.now());
        ruleMapper.updateById(rule);
        return rule;
    }

    @Override
    @Transactional
    public void deleteRule(Long userId, Long ruleId) {
        if (ruleMapper.selectById(ruleId) == null) throw new BusinessException("告警规则不存在: " + ruleId);
        requireOwned(userId, ruleMapper.selectById(ruleId));
        ruleMapper.deleteById(ruleId);
    }

    @Override
    public AgentAlertRule getRule(Long ruleId) {
        return ruleMapper.selectById(ruleId);
    }

    @Override
    public List<AgentAlertRule> listRules(Long userId) {
        List<AgentAlertRule> rules = new ArrayList<>();
        // User-specific rules
        if (userId != null) {
            LambdaQueryWrapper<AgentAlertRule> userQuery = new LambdaQueryWrapper<>();
            userQuery.eq(AgentAlertRule::getUserId, userId);
            rules.addAll(ruleMapper.selectList(userQuery));
        }
        // Global rules (user_id IS NULL)
        LambdaQueryWrapper<AgentAlertRule> globalQuery = new LambdaQueryWrapper<>();
        globalQuery.isNull(AgentAlertRule::getUserId);
        rules.addAll(ruleMapper.selectList(globalQuery));
        return rules;
    }

    // ================================================================
    // 告警事件查询
    // ================================================================

    @Override
    public PageResult<AgentAlertEvent> listAlertEvents(Long userId, int page, int pageSize) {
        LambdaQueryWrapper<AgentAlertEvent> query = new LambdaQueryWrapper<>();
        if (userId != null) query.eq(AgentAlertEvent::getUserId, userId);
        query.orderByDesc(AgentAlertEvent::getCreatedAt);

        long total = eventMapper.selectCount(query);
        int offset = (page - 1) * pageSize;
        List<AgentAlertEvent> events = eventMapper.selectList(query.last("LIMIT " + offset + "," + pageSize));
        return PageResult.of(page, pageSize, Math.toIntExact(total), events);
    }

    @Override
    public List<AgentAlertEvent> listUnresolvedAlerts(Long userId) {
        LambdaQueryWrapper<AgentAlertEvent> query = new LambdaQueryWrapper<>();
        query.eq(AgentAlertEvent::getResolved, false);
        if (userId != null) query.eq(AgentAlertEvent::getUserId, userId);
        query.orderByDesc(AgentAlertEvent::getCreatedAt);
        // 防御性上限：未解决告警长期不处理时该列表会无界增长（R16-10）
        query.last("LIMIT 500");
        return eventMapper.selectList(query);
    }

    @Override
    @Transactional
    public void resolveAlert(Long userId, Long alertId) {
        AgentAlertEvent event = eventMapper.selectById(alertId);
        if (event != null && (userId == null || !userId.equals(event.getUserId()))) {
            throw new BusinessException("unauthorized alert");
        }
        if (event == null) throw new BusinessException("告警事件不存在: " + alertId);
        event.setResolved(true);
        event.setResolvedAt(LocalDateTime.now());
        eventMapper.updateById(event);
    }

    // ================================================================
    // 告警检查
    // ================================================================

    @Override
    public List<AgentAlertEvent> checkAlerts(Long userId) {
        List<AgentAlertRule> rules = listRules(userId);
        List<AgentAlertEvent> newEvents = new ArrayList<>();

        for (AgentAlertRule rule : rules) {
            if (!Boolean.TRUE.equals(rule.getEnabled())) continue;

            // Cooldown check
            if (rule.getLastTriggeredAt() != null) {
                long minutesSince = ChronoUnit.MINUTES.between(rule.getLastTriggeredAt(), LocalDateTime.now());
                int cooldown = rule.getCooldownMinutes() != null ? rule.getCooldownMinutes() : 60;
                if (minutesSince < cooldown) continue;
            }

            // Evaluate
            try {
                AlertEvalResult result = evaluateMetric(userId, rule);
                if (result.triggered) {
                    AgentAlertEvent event = createAlertEvent(rule, userId, result);
                    eventMapper.insert(event);
                    // Update last triggered time
                    rule.setLastTriggeredAt(LocalDateTime.now());
                    ruleMapper.updateById(rule);
                    newEvents.add(event);
                    log.warn(
                            "Alert triggered: rule={} metric={} current={} threshold={}",
                            rule.getName(),
                            rule.getMetricName(),
                            result.currentValue,
                            rule.getThresholdValue());
                }
            } catch (Exception e) {
                log.error("Alert evaluation failed for rule {}: {}", rule.getId(), e.getMessage());
            }
        }

        return newEvents;
    }

    @Override
    public List<AgentAlertEvent> checkAllActiveAlerts() {
        // Get all unique user IDs that have tasks
        LambdaQueryWrapper<AgentTask> taskQuery = new LambdaQueryWrapper<>();
        taskQuery.select(AgentTask::getUserId).groupBy(AgentTask::getUserId);
        List<AgentTask> tasks = taskMapper.selectList(taskQuery);
        Set<Long> activeUserIds = new HashSet<>();
        for (AgentTask t : tasks) {
            if (t.getUserId() != null) activeUserIds.add(t.getUserId());
        }

        List<AgentAlertEvent> allEvents = new ArrayList<>();
        for (Long userId : activeUserIds) {
            allEvents.addAll(checkAlerts(userId));
        }
        return allEvents;
    }

    // ================================================================
    // 指标评估逻辑
    // ================================================================

    private AlertEvalResult evaluateMetric(Long userId, AgentAlertRule rule) {
        return switch (rule.getMetricName()) {
            case "citation_miss_rate" -> evalCitationMissRate(userId, rule);
            case "tool_failure_rate" -> evalToolFailureRate(userId, rule);
            case "running_timeout" -> evalRunningTimeout(userId, rule);
            case "approval_timeout" -> evalApprovalTimeout(userId, rule);
            default -> new AlertEvalResult(false, 0.0, "unknown_metric");
        };
    }

    private AlertEvalResult evalCitationMissRate(Long userId, AgentAlertRule rule) {
        int windowMinutes = rule.getWindowMinutes() != null ? rule.getWindowMinutes() : 1440;
        LocalDateTime windowStart = LocalDateTime.now().minusMinutes(windowMinutes);

        List<AgentRun> runs = getRunsInWindow(userId, windowStart);
        long completed =
                runs.stream().filter(r -> "succeeded".equals(r.getStatus())).count();
        if (completed == 0) return new AlertEvalResult(false, 0.0, "insufficient_data");

        // Check each completed run's steps for sources
        long missingCitations = 0;
        for (AgentRun r : runs) {
            if (!"succeeded".equals(r.getStatus())) continue;
            List<AgentStep> steps = stepMapper.selectByRunId(r.getId());
            boolean hasSources = steps.stream()
                    .anyMatch(s -> s.getSources() != null && !s.getSources().isEmpty());
            if (!hasSources && !steps.isEmpty()) missingCitations++;
        }

        double rate = (double) missingCitations / completed;
        boolean triggered = compareValue(rate, rule.getThresholdValue(), rule.getComparisonOperator());
        return new AlertEvalResult(triggered, rate, "citation_miss_rate=" + String.format("%.4f", rate));
    }

    private AlertEvalResult evalToolFailureRate(Long userId, AgentAlertRule rule) {
        int windowMinutes = rule.getWindowMinutes() != null ? rule.getWindowMinutes() : 60;
        LocalDateTime windowStart = LocalDateTime.now().minusMinutes(windowMinutes);

        List<AgentRun> runs = getRunsInWindow(userId, windowStart);
        long total = runs.size();
        if (total == 0) return new AlertEvalResult(false, 0.0, "insufficient_data");

        long failures = runs.stream()
                .filter(r -> "failed".equals(r.getStatus()) || "tool_error".equals(r.getStatus()))
                .count();

        double rate = (double) failures / total;
        boolean triggered = compareValue(rate, rule.getThresholdValue(), rule.getComparisonOperator());
        return new AlertEvalResult(
                triggered, rate, "failures=" + failures + " total=" + total + " rate=" + String.format("%.4f", rate));
    }

    private AlertEvalResult evalRunningTimeout(Long userId, AgentAlertRule rule) {
        int windowMinutes = rule.getWindowMinutes() != null ? rule.getWindowMinutes() : 5;
        LocalDateTime timeoutThreshold = LocalDateTime.now().minusSeconds(120);

        // Find runs stuck in running state
        LambdaQueryWrapper<AgentTask> taskQuery = new LambdaQueryWrapper<>();
        taskQuery.eq(AgentTask::getUserId, userId).eq(AgentTask::getStatus, "running");
        List<AgentTask> runningTasks = taskMapper.selectList(taskQuery);

        long staleCount = 0;
        for (AgentTask t : runningTasks) {
            if (t.getUpdatedAt() != null && t.getUpdatedAt().isBefore(timeoutThreshold)) {
                staleCount++;
            }
        }

        boolean triggered = staleCount > 0
                && compareValue((double) staleCount, rule.getThresholdValue(), rule.getComparisonOperator());
        return new AlertEvalResult(triggered, (double) staleCount, "stale_running_tasks=" + staleCount);
    }

    private AlertEvalResult evalApprovalTimeout(Long userId, AgentAlertRule rule) {
        LocalDateTime threshold = LocalDateTime.now().minusMinutes(4);

        LambdaQueryWrapper<AgentApproval> query = new LambdaQueryWrapper<>();
        query.eq(AgentApproval::getStatus, "pending")
                .eq(AgentApproval::getUserId, userId)
                .lt(AgentApproval::getCreatedAt, threshold);
        List<AgentApproval> staleApprovals = approvalMapper.selectList(query);

        long count = staleApprovals.size();
        boolean triggered =
                count > 0 && compareValue((double) count, rule.getThresholdValue(), rule.getComparisonOperator());
        return new AlertEvalResult(triggered, (double) count, "stale_pending_approvals=" + count);
    }

    // ================================================================
    // 工具方法
    // ================================================================

    private List<AgentRun> getRunsInWindow(Long userId, LocalDateTime windowStart) {
        LambdaQueryWrapper<AgentTask> taskQuery = new LambdaQueryWrapper<>();
        taskQuery.eq(AgentTask::getUserId, userId);
        List<Long> taskIds =
                taskMapper.selectList(taskQuery).stream().map(AgentTask::getId).toList();
        if (taskIds.isEmpty()) return List.of();

        LambdaQueryWrapper<AgentRun> runQuery = new LambdaQueryWrapper<>();
        runQuery.in(AgentRun::getTaskId, taskIds).ge(AgentRun::getStartedAt, windowStart);
        return runMapper.selectList(runQuery);
    }

    private boolean compareValue(double current, double threshold, String operator) {
        if (operator == null) operator = "gte";
        return switch (operator) {
            case "gt" -> current > threshold;
            case "gte" -> current >= threshold;
            case "lt" -> current < threshold;
            case "lte" -> current <= threshold;
            case "eq" -> Math.abs(current - threshold) < 0.0001;
            default -> current >= threshold;
        };
    }

    private AgentAlertEvent createAlertEvent(AgentAlertRule rule, Long userId, AlertEvalResult result) {
        AgentAlertEvent event = new AgentAlertEvent();
        event.setRuleId(rule.getId());
        event.setRuleName(rule.getName());
        event.setUserId(userId);
        event.setSeverity(rule.getSeverity() != null ? rule.getSeverity() : "warning");
        event.setMetricName(rule.getMetricName());
        event.setCurrentValue(result.currentValue);
        event.setThresholdValue(rule.getThresholdValue());
        event.setMessage(buildAlertMessage(rule, result));
        event.setResolved(false);
        event.setCreatedAt(LocalDateTime.now());
        return event;
    }

    private String buildAlertMessage(AgentAlertRule rule, AlertEvalResult result) {
        return String.format(
                "[%s] %s: current=%.4f threshold=%.4f (%s) — %s",
                rule.getSeverity(),
                rule.getName(),
                result.currentValue,
                rule.getThresholdValue(),
                rule.getComparisonOperator(),
                result.context);
    }

    // ── 内部评估结果 ──

    private void requireOwned(Long userId, AgentAlertRule rule) {
        if (rule == null || userId == null || rule.getUserId() == null || !userId.equals(rule.getUserId())) {
            throw new BusinessException("unauthorized alert rule");
        }
    }

    private record AlertEvalResult(boolean triggered, double currentValue, String context) {}
}
