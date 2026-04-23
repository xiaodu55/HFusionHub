package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import lombok.Data;

/**
 * 按模型分组的成本统计
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "按模型分组的成本统计")
public class ModelCostDTO {

    @Schema(description = "模型名称")
    private String model;

    @Schema(description = "请求次数")
    private Long requestCount;

    @Schema(description = "总 tokens")
    private Long totalTokens;

    @Schema(description = "总成本（美元）")
    private BigDecimal totalCost;
}
