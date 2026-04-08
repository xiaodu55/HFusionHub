package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/**
 * 当前用户成本汇总
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "当前用户成本汇总")
public class CostSummaryDTO {

    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "统计起始时间")
    private LocalDateTime periodStart;

    @Schema(description = "统计结束时间")
    private LocalDateTime periodEnd;

    @Schema(description = "期间总成本（美元）")
    private BigDecimal totalCost;

    @Schema(description = "期间总 tokens")
    private Long totalTokens;

    @Schema(description = "期间请求次数")
    private Long totalRequests;

    @Schema(description = "本月已发生成本（美元）")
    private BigDecimal currentMonthCost;

    @Schema(description = "本月预估成本（美元，按已过天数外推）")
    private BigDecimal estimatedMonthCost;

    @Schema(description = "按模型分组明细")
    private List<ModelCostDTO> modelBreakdown;
}
