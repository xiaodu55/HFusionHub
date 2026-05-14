package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.AgentAggregatedStatsDTO;
import com.hfusionhub.dto.AgentMetricsDTO;
import com.hfusionhub.dto.AgentMetricsSummaryDTO;
import com.hfusionhub.entity.AgentRun;
import com.hfusionhub.entity.AgentStep;
import com.hfusionhub.entity.AgentTask;
import com.hfusionhub.mapper.AgentApprovalMapper;
import com.hfusionhub.mapper.AgentRunMapper;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.mapper.AgentTaskMapper;
import com.hfusionhub.service.AgentMetricsService;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

/**
 * Agent 指标聚合与查询服务实现
 *
 * 查询已有的 agent_task + agent_run + agent_step 表进行聚合，
 * 不依赖额外的汇总表。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentMetricsServiceImpl implements AgentMetricsService {

    private final AgentTaskMapper taskMapper;
    private final AgentRunMapper runMapper;
    private final AgentStepMapper stepMapper;
    private final AgentApprovalMapper approvalMapper;

    // ================================================================
    // 单任务 / 单 Run 指标
    // ================================================================

    @Override
    public AgentMetricsDTO getTaskMetrics(Long userId, Long taskId) {
        AgentTask task = taskMapper.selectById(taskId);
        if (task == null || userId == null || !userId.equals(task.getUserId())) return null;

        List<AgentRun> runs = runMapper.selectByTaskId(taskId);

        long totalDuration = 0L;
        int totalToolCalls = 0;
        int totalSources = 0;
        int totalSteps = 0;
        long totalApprovalDuration = 0L;
        int approvalCount = 0;
        long totalTokens = 0L;
        long promptTokens = 0L;
        long completionTokens = 0L;
        String lastErrorCode = null;
        String lastErrorDetail = null;
        String lastFailedTool = null;
        String model = null;

        for (AgentRun run : runs) {
            if (run.getDurationMs() != null) totalDuration += run.getDurationMs();
            if (run.getToolCallsCount() != null) totalToolCalls += run.getToolCallsCount();
            if (run.getErrorCode() != null) {
                lastErrorCode = run.getErrorCode();
                lastErrorDetail = run.getErrorDetail();
                lastFailedTool = run.getFailedTool();
            }
            if (run.getModel() != null) model = run.getModel();
            if (run.getTokenUsage() != null) {
                Map<String, Object> tu = run.getTokenUsage();
                totalTokens += toLong(tu.get("total_tokens"));
                promptTokens += toLong(tu.get("prompt_tokens"));
                completionTokens += toLong(tu.get("completion_tokens"));
            }

            // step-level aggregation
            List<AgentStep> steps = stepMapper.selectByRunId(run.getId());
            totalSteps += steps.size();
            totalSources += steps.stream()
                    .filter(s -> s.getSources() != null)
                    .mapToInt(s -> s.getSources().size())
                    .sum();
        }

        int runCount = Math.max(runs.size(), 1);
        return AgentMetricsDTO.builder()
                .taskId(taskId)
                .status(task.getStatus())
                .totalDurationMs(totalDuration)
                .avgStepLatencyMs(totalSteps > 0 ? totalDuration / totalSteps : 0L)
                .totalTokens(totalTokens)
                .promptTokens(promptTokens)
                .completionTokens(completionTokens)
                .toolCallsCount(totalToolCalls)
                .sourcesCount(totalSources)
                .stepCount(totalSteps)
                .approvalCount(approvalCount)
                .avgApprovalDurationMs(approvalCount > 0 ? totalApprovalDuration / approvalCount : 0L)
                .errorCode(lastErrorCode)
                .errorDetail(lastErrorDetail)
                .failedTool(lastFailedTool)
                .model(model)
                .build();
    }

    @Override
    public AgentMetricsDTO getRunMetrics(Long userId, Long runId) {
        AgentRun run = runMapper.selectById(runId);
        if (run == null) return null;
        AgentTask ownerTask = taskMapper.selectById(run.getTaskId());
        if (ownerTask == null || userId == null || !userId.equals(ownerTask.getUserId())) return null;

        List<AgentStep> steps = stepMapper.selectByRunId(runId);

        long avgStepMs = 0L;
        long maxStepMs = 0L;
        int sourcesCount = 0;

        if (!steps.isEmpty()) {
            long totalStepMs = steps.stream()
                    .mapToLong(s -> s.getDurationMs() != null ? s.getDurationMs() : 0L)
                    .sum();
            avgStepMs = totalStepMs / steps.size();
            maxStepMs = steps.stream()
                    .mapToLong(s -> s.getDurationMs() != null ? s.getDurationMs() : 0L)
                    .max()
                    .orElse(0L);
            sourcesCount = steps.stream()
                    .filter(s -> s.getSources() != null)
                    .mapToInt(s -> s.getSources().size())
                    .sum();
        }

        long totalTokens = 0L;
        long promptTokens = 0L;
        long completionTokens = 0L;
        if (run.getTokenUsage() != null) {
            Map<String, Object> tu = run.getTokenUsage();
            totalTokens = toLong(tu.get("total_tokens"));
            promptTokens = toLong(tu.get("prompt_tokens"));
            completionTokens = toLong(tu.get("completion_tokens"));
        }

        // approval count & duration for this run
        LambdaQueryWrapper<com.hfusionhub.entity.AgentApproval> approvalQuery = new LambdaQueryWrapper<>();
        approvalQuery.eq(com.hfusionhub.entity.AgentApproval::getRunId, runId);
        var approvals = approvalMapper.selectList(approvalQuery);
        int approvalCount = approvals != null ? approvals.size() : 0;
        long totalApprovalMs = 0L;
        if (approvals != null) {
            for (var a : approvals) {
                if (a.getCreatedAt() != null && a.getDecidedAt() != null) {
                    totalApprovalMs += ChronoUnit.MILLIS.between(a.getCreatedAt(), a.getDecidedAt());
                }
            }
        }

        return AgentMetricsDTO.builder()
                .runId(runId)
                .runUuid(run.getRunUuid())
                .taskId(run.getTaskId())
                .status(run.getStatus())
                .totalDurationMs(run.getDurationMs())
                .avgStepLatencyMs(avgStepMs)
                .maxStepLatencyMs(maxStepMs)
                .totalTokens(totalTokens)
                .promptTokens(promptTokens)
                .completionTokens(completionTokens)
                .toolCallsCount(run.getToolCallsCount())
                .sourcesCount(sourcesCount)
                .stepCount(steps.size())
                .approvalCount(approvalCount)
                .avgApprovalDurationMs(approvalCount > 0 ? totalApprovalMs / approvalCount : 0L)
                .errorCode(run.getErrorCode())
                .errorDetail(run.getErrorDetail())
                .failedTool(run.getFailedTool())
                .model(run.getModel())
                .style(run.getStyle())
                .maxToolSteps(run.getMaxToolSteps())
                .tokenUsage(run.getTokenUsage())
                .build();
    }

    // ================================================================
    // Run 指标列表（分页 + 筛选）
    // ================================================================

    @Override
    public PageResult<AgentMetricsSummaryDTO> listRunMetrics(
            Long userId, Long kbId, String status, LocalDateTime start, LocalDateTime end, int page, int pageSize) {

        // Build task IDs filter
        Set<Long> allowedTaskIds = null;
        if (userId != null || kbId != null) {
            LambdaQueryWrapper<AgentTask> taskQuery = new LambdaQueryWrapper<>();
            if (userId != null) taskQuery.eq(AgentTask::getUserId, userId);
            if (kbId != null) taskQuery.eq(AgentTask::getKnowledgeBaseId, kbId);
            List<AgentTask> tasks = taskMapper.selectList(taskQuery);
            allowedTaskIds = tasks.stream().map(AgentTask::getId).collect(Collectors.toSet());
            if (allowedTaskIds.isEmpty()) {
                return PageResult.of(page, pageSize, 0, List.of());
            }
        }

        // Build run query
        LambdaQueryWrapper<AgentRun> query = new LambdaQueryWrapper<>();
        if (allowedTaskIds != null) query.in(AgentRun::getTaskId, allowedTaskIds);
        if (status != null && !status.isBlank()) query.eq(AgentRun::getStatus, status);
        if (start != null) query.ge(AgentRun::getStartedAt, start);
        if (end != null) query.le(AgentRun::getStartedAt, end);
        query.orderByDesc(AgentRun::getCreatedAt);

        long total = runMapper.selectCount(query);
        int offset = (page - 1) * pageSize;
        // MyBatis Plus pagination via LIMIT
        List<AgentRun> runs = runMapper.selectList(query.last("LIMIT " + offset + "," + pageSize));

        // Build task lookup for query text (batch query instead of N+1 selectById)
        Map<Long, AgentTask> taskMap = new HashMap<>();
        List<Long> taskIds = runs.stream().map(AgentRun::getTaskId).distinct().toList();
        if (!taskIds.isEmpty()) {
            for (AgentTask task : taskMapper.selectBatchIds(taskIds)) {
                taskMap.put(task.getId(), task);
            }
        }

        // Batch-fetch all steps for the page's runs (instead of per-run selectByRunId N+1)
        Map<Long, List<AgentStep>> stepsByRunId = new HashMap<>();
        List<Long> runIds = runs.stream().map(AgentRun::getId).distinct().toList();
        if (!runIds.isEmpty()) {
            for (AgentStep step : stepMapper.selectByRunIds(runIds)) {
                stepsByRunId.computeIfAbsent(step.getRunId(), k -> new ArrayList<>()).add(step);
            }
        }

        List<AgentMetricsSummaryDTO> summaries = runs.stream()
                .map(run -> {
                    AgentTask task = taskMap.get(run.getTaskId());
                    String querySummary = null;
                    Long kbIdOut = null;
                    if (task != null) {
                        querySummary = task.getQuery();
                        if (querySummary != null && querySummary.length() > 100) {
                            querySummary = querySummary.substring(0, 97) + "...";
                        }
                        kbIdOut = task.getKnowledgeBaseId();
                    }

                    // count sources for this run
                    List<AgentStep> steps = stepsByRunId.getOrDefault(run.getId(), List.of());
                    int sourcesCount = steps.stream()
                            .filter(s -> s.getSources() != null)
                            .mapToInt(s -> s.getSources().size())
                            .sum();

                    long totalTokens = 0L;
                    if (run.getTokenUsage() != null) {
                        totalTokens = toLong(run.getTokenUsage().get("total_tokens"));
                    }

                    return AgentMetricsSummaryDTO.builder()
                            .runId(run.getId())
                            .runUuid(run.getRunUuid())
                            .taskId(run.getTaskId())
                            .knowledgeBaseId(kbIdOut)
                            .querySummary(querySummary)
                            .status(run.getStatus())
                            .model(run.getModel())
                            .durationMs(run.getDurationMs())
                            .totalTokens(totalTokens)
                            .toolCallsCount(run.getToolCallsCount())
                            .sourcesCount(sourcesCount)
                            .errorCode(run.getErrorCode())
                            .startedAt(run.getStartedAt())
                            .completedAt(run.getCompletedAt())
                            .build();
                })
                .collect(Collectors.toList());

        return PageResult.of(page, pageSize, Math.toIntExact(total), summaries);
    }

    // ================================================================
    // 聚合统计
    // ================================================================

    @Override
    public AgentAggregatedStatsDTO getAggregatedStats(Long userId, Long kbId, int days) {

        LocalDateTime periodStart = LocalDateTime.now().minusDays(Math.max(1, Math.min(days, 30)));

        // Collect all runs in the window
        LambdaQueryWrapper<AgentRun> query = new LambdaQueryWrapper<>();
        query.ge(AgentRun::getStartedAt, periodStart);

        // Task-level filter
        LambdaQueryWrapper<AgentTask> taskQuery = new LambdaQueryWrapper<>();
        if (userId != null) taskQuery.eq(AgentTask::getUserId, userId);
        if (kbId != null) taskQuery.eq(AgentTask::getKnowledgeBaseId, kbId);

        List<AgentTask> tasks = taskMapper.selectList(taskQuery);
        Set<Long> taskIds = tasks.stream().map(AgentTask::getId).collect(Collectors.toSet());

        if (taskIds.isEmpty() && (userId != null || kbId != null)) {
            return buildEmptyStats(userId, kbId, periodStart);
        }

        if (!taskIds.isEmpty()) {
            query.in(AgentRun::getTaskId, taskIds);
        }

        List<AgentRun> runs = runMapper.selectList(query);

        return buildStatsFromRuns(runs, userId, kbId, periodStart, days);
    }

    // ================================================================
    // Dashboard 概览
    // ================================================================

    @Override
    public Map<String, Object> getDashboardStats(Long userId) {
        LocalDateTime todayStart = LocalDateTime.now().truncatedTo(ChronoUnit.DAYS);
        LocalDateTime weekAgo = LocalDateTime.now().minusDays(7);

        // Today's runs
        LambdaQueryWrapper<AgentTask> taskQuery = new LambdaQueryWrapper<>();
        taskQuery.eq(AgentTask::getUserId, userId);
        List<AgentTask> userTasks = taskMapper.selectList(taskQuery);
        Set<Long> taskIds = userTasks.stream().map(AgentTask::getId).collect(Collectors.toSet());

        if (taskIds.isEmpty()) {
            return Map.of(
                    "todayRuns",
                    0,
                    "todayErrors",
                    0,
                    "todayAvgLatencyMs",
                    0L,
                    "recentRunCount",
                    0,
                    "recentFailureRate",
                    0.0,
                    "activeTasks",
                    0,
                    "pendingApprovals",
                    0);
        }

        // Today
        LambdaQueryWrapper<AgentRun> todayQuery = new LambdaQueryWrapper<>();
        todayQuery.in(AgentRun::getTaskId, taskIds).ge(AgentRun::getStartedAt, todayStart);
        List<AgentRun> todayRuns = runMapper.selectList(todayQuery);

        // Last 7 days
        LambdaQueryWrapper<AgentRun> weekQuery = new LambdaQueryWrapper<>();
        weekQuery.in(AgentRun::getTaskId, taskIds).ge(AgentRun::getStartedAt, weekAgo);
        List<AgentRun> weekRuns = runMapper.selectList(weekQuery);

        long todayAvgMs = todayRuns.isEmpty()
                ? 0L
                : todayRuns.stream()
                                .mapToLong(r -> r.getDurationMs() != null ? r.getDurationMs() : 0L)
                                .sum()
                        / todayRuns.size();
        long todayErrors =
                todayRuns.stream().filter(r -> r.getErrorCode() != null).count();

        long weekFailures =
                weekRuns.stream().filter(r -> r.getErrorCode() != null).count();
        double weekFailureRate = weekRuns.isEmpty() ? 0.0 : (double) weekFailures / weekRuns.size();

        // Active tasks (pending or running)
        long activeTasks = userTasks.stream()
                .filter(t -> "pending".equals(t.getStatus()) || "running".equals(t.getStatus()))
                .count();

        // Pending approvals
        LambdaQueryWrapper<com.hfusionhub.entity.AgentApproval> pendingQuery = new LambdaQueryWrapper<>();
        pendingQuery
                .eq(com.hfusionhub.entity.AgentApproval::getStatus, "pending")
                .eq(com.hfusionhub.entity.AgentApproval::getUserId, userId);
        int pendingApprovals = Math.toIntExact(approvalMapper.selectCount(pendingQuery));

        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("todayRuns", todayRuns.size());
        stats.put("todayErrors", (int) todayErrors);
        stats.put("todayAvgLatencyMs", todayAvgMs);
        stats.put("recentRunCount", weekRuns.size());
        stats.put("recentFailureRate", Math.round(weekFailureRate * 10000.0) / 10000.0);
        stats.put("activeTasks", (int) activeTasks);
        stats.put("pendingApprovals", pendingApprovals);
        return stats;
    }

    // ================================================================
    // 内部辅助方法
    // ================================================================

    private static long toLong(Object value) {
        if (value instanceof Number n) return n.longValue();
        if (value instanceof String s) {
            try {
                return Long.parseLong(s);
            } catch (NumberFormatException ignored) {
            }
        }
        return 0L;
    }

    private AgentAggregatedStatsDTO buildEmptyStats(Long userId, Long kbId, LocalDateTime periodStart) {
        return AgentAggregatedStatsDTO.builder()
                .userId(userId)
                .knowledgeBaseId(kbId)
                .periodStart(periodStart)
                .periodEnd(LocalDateTime.now())
                .totalTasks(0)
                .totalRuns(0)
                .successCount(0)
                .failureCount(0)
                .timeoutCount(0)
                .cancelledCount(0)
                .successRate(0.0)
                .failureRate(0.0)
                .avgDurationMs(0L)
                .p50DurationMs(0L)
                .p95DurationMs(0L)
                .maxDurationMs(0L)
                .avgToolCalls(0.0)
                .totalPromptTokens(0L)
                .totalCompletionTokens(0L)
                .totalTokens(0L)
                .avgTokensPerRun(0.0)
                .avgApprovalDurationMs(0L)
                .dailyMetrics(List.of())
                .build();
    }

    private AgentAggregatedStatsDTO buildStatsFromRuns(
            List<AgentRun> runs, Long userId, Long kbId, LocalDateTime periodStart, int days) {

        int total = runs.size();
        if (total == 0) return buildEmptyStats(userId, kbId, periodStart);

        int successCount = 0, failureCount = 0, timeoutCount = 0, cancelledCount = 0;
        long totalDuration = 0L;
        long totalToolCalls = 0L;
        long totalPromptTokens = 0L, totalCompletionTokens = 0L, totalTokens = 0L;
        List<Long> durations = new ArrayList<>();

        for (AgentRun run : runs) {
            String s = run.getStatus();
            if ("succeeded".equals(s)) successCount++;
            else if ("failed".equals(s)) failureCount++;
            else if ("timed_out".equals(s)) timeoutCount++;
            else if ("cancelled".equals(s)) cancelledCount++;

            long dur = run.getDurationMs() != null ? run.getDurationMs() : 0L;
            if (dur > 0) durations.add(dur);
            totalDuration += dur;
            if (run.getToolCallsCount() != null) totalToolCalls += run.getToolCallsCount();

            if (run.getTokenUsage() != null) {
                Map<String, Object> tu = run.getTokenUsage();
                totalPromptTokens += toLong(tu.get("prompt_tokens"));
                totalCompletionTokens += toLong(tu.get("completion_tokens"));
                totalTokens += toLong(tu.get("total_tokens"));
            }
        }

        Collections.sort(durations);
        long p50 = durations.isEmpty() ? 0L : durations.get(durations.size() / 2);
        long p95 = durations.isEmpty() ? 0L : durations.get((int) (durations.size() * 0.95));

        // Daily breakdown
        Map<java.time.LocalDate, List<AgentRun>> byDay = runs.stream()
                .filter(r -> r.getStartedAt() != null)
                .collect(Collectors.groupingBy(r -> r.getStartedAt().toLocalDate()));

        List<AgentAggregatedStatsDTO.DailyMetricDTO> dailyMetrics = new ArrayList<>();
        for (int i = 0; i < days; i++) {
            java.time.LocalDate date = java.time.LocalDate.now().minusDays(days - 1 - i);
            List<AgentRun> dayRuns = byDay.getOrDefault(date, List.of());
            int dc = dayRuns.size();
            int ds = (int) dayRuns.stream()
                    .filter(r -> "succeeded".equals(r.getStatus()))
                    .count();
            int df = (int)
                    dayRuns.stream().filter(r -> "failed".equals(r.getStatus())).count();
            long dDur = dayRuns.stream()
                    .mapToLong(r -> r.getDurationMs() != null ? r.getDurationMs() : 0L)
                    .sum();
            double dTc = dayRuns.stream()
                    .mapToInt(r -> r.getToolCallsCount() != null ? r.getToolCallsCount() : 0)
                    .average()
                    .orElse(0.0);
            double dTok = dayRuns.stream()
                    .mapToLong(r -> {
                        if (r.getTokenUsage() != null)
                            return toLong(r.getTokenUsage().get("total_tokens"));
                        return 0L;
                    })
                    .average()
                    .orElse(0.0);

            dailyMetrics.add(AgentAggregatedStatsDTO.DailyMetricDTO.builder()
                    .date(date.toString())
                    .runCount(dc)
                    .successCount(ds)
                    .failureCount(df)
                    .avgDurationMs(dc > 0 ? dDur / dc : 0L)
                    .avgToolCalls(Math.round(dTc * 100.0) / 100.0)
                    .avgTokens(Math.round(dTok * 100.0) / 100.0)
                    .build());
        }

        return AgentAggregatedStatsDTO.builder()
                .userId(userId)
                .knowledgeBaseId(kbId)
                .periodStart(periodStart)
                .periodEnd(LocalDateTime.now())
                .totalTasks(
                        (int) runs.stream().map(AgentRun::getTaskId).distinct().count())
                .totalRuns(total)
                .successCount(successCount)
                .failureCount(failureCount)
                .timeoutCount(timeoutCount)
                .cancelledCount(cancelledCount)
                .successRate(total > 0 ? (double) successCount / total : 0.0)
                .failureRate(total > 0 ? (double) (failureCount + timeoutCount) / total : 0.0)
                .avgDurationMs(total > 0 ? totalDuration / total : 0L)
                .p50DurationMs(p50)
                .p95DurationMs(p95)
                .maxDurationMs(durations.isEmpty() ? 0L : durations.get(durations.size() - 1))
                .avgToolCalls(total > 0 ? (double) totalToolCalls / total : 0.0)
                .totalPromptTokens(totalPromptTokens)
                .totalCompletionTokens(totalCompletionTokens)
                .totalTokens(totalTokens)
                .avgTokensPerRun(total > 0 ? (double) totalTokens / total : 0.0)
                .avgApprovalDurationMs(0L)
                .dailyMetrics(dailyMetrics)
                .build();
    }
}
