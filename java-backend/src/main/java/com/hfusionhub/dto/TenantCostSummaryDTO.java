package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import lombok.Data;

/**
 * 租户级成本汇总
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "租户级成本汇总")
public class TenantCostSummaryDTO {

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "统计起始时间")
    private LocalDateTime startDate;

    @Schema(description = "统计结束时间")
    private LocalDateTime endDate;

    @Schema(description = "总成本（美元）")
    private BigDecimal totalCost;

    @Schema(description = "总 tokens")
    private Long totalTokens;

    @Schema(description = "总请求次数")
    private Long totalRequests;

    @Schema(description = "按模型分组明细")
    private List<ModelCostDTO> modelBreakdown;
}
