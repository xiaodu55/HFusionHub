package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * 每日成本统计（图表数据）
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "每日成本统计")
public class DailyCostDTO {

    @Schema(description = "统计日期")
    private LocalDate statDate;

    @Schema(description = "请求次数")
    private Long requestCount;

    @Schema(description = "总 tokens")
    private Long totalTokens;

    @Schema(description = "总成本（美元）")
    private BigDecimal totalCost;

    @Schema(description = "平均延迟（毫秒）")
    private Long avgLatencyMs;
}
