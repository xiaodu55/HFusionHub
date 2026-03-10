package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Agent 聚合统计DTO — 按用户/KB/时间窗口汇总
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "Agent聚合统计")
public class AgentAggregatedStatsDTO {

    @Schema(description = "用户ID(可选)")
    private Long userId;

    @Schema(description = "知识库ID(可选)")
    private Long knowledgeBaseId;

    @Schema(description = "统计窗口开始")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime periodStart;

    @Schema(description = "统计窗口结束")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime periodEnd;

    @Schema(description = "总任务数")
    private Integer totalTasks;

    @Schema(description = "总Run数")
    private Integer totalRuns;

    @Schema(description = "成功数")
    private Integer successCount;

    @Schema(description = "失败数")
    private Integer failureCount;

    @Schema(description = "超时数")
    private Integer timeoutCount;

    @Schema(description = "取消数")
    private Integer cancelledCount;

    @Schema(description = "成功率")
    private Double successRate;

    @Schema(description = "失败率")
    private Double failureRate;

    @Schema(description = "平均耗时(ms)")
    private Long avgDurationMs;

    @Schema(description = "P50耗时(ms)")
    private Long p50DurationMs;

    @Schema(description = "P95耗时(ms)")
    private Long p95DurationMs;

    @Schema(description = "最大耗时(ms)")
    private Long maxDurationMs;

    @Schema(description = "平均工具调用次数")
    private Double avgToolCalls;

    @Schema(description = "总Prompt Token")
    private Long totalPromptTokens;

    @Schema(description = "总Completion Token")
    private Long totalCompletionTokens;

    @Schema(description = "总Token")
    private Long totalTokens;

    @Schema(description = "平均Token/Run")
    private Double avgTokensPerRun;

    @Schema(description = "平均审批耗时(ms)")
    private Long avgApprovalDurationMs;

    @Schema(description = "每日指标时间序列")
    private List<DailyMetricDTO> dailyMetrics;

    // ── 内嵌类 ──

    @Data
    @Builder
    @Schema(description = "每日指标")
    public static class DailyMetricDTO {
        @Schema(description = "日期")
        private String date;
        @Schema(description = "Run数")
        private Integer runCount;
        @Schema(description = "成功数")
        private Integer successCount;
        @Schema(description = "失败数")
        private Integer failureCount;
        @Schema(description = "平均耗时(ms)")
        private Long avgDurationMs;
        @Schema(description = "平均工具调用")
        private Double avgToolCalls;
        @Schema(description = "平均Token")
        private Double avgTokens;
    }
}
