package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

/**
 * 租户配额摘要（单计量项）
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "租户配额摘要")
public class QuotaSummaryDTO {

    @Schema(description = "计量项代码: chat_tokens|agent_tokens|index_chunks|plugin_executions")
    private String meter;

    @Schema(description = "计量项显示名")
    private String label;

    @Schema(description = "单位显示名：Token / 次")
    private String unit;

    @Schema(description = "今日已结算用量")
    private long committed;

    @Schema(description = "今日已预占未结算用量")
    private long reserved;

    @Schema(description = "今日总用量（committed + reserved）")
    private long used;

    @Schema(description = "有效日限额（租户覆盖优先，否则计划档默认）")
    private long dailyLimit;

    @Schema(description = "今日剩余额度（不低于 0）")
    private long remaining;

    @Schema(description = "用量百分比（0-100，超限可超过 100）")
    private double percent;
}
