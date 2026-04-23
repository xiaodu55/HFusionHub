package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 评测回归门禁结果
 *
 * <p>门禁规则：accuracy &gt; 0.8 且 latency_p95 &lt; 5000ms 且
 * token_cost &lt; 基线 token 成本 × 1.2（基线为同数据集最近一次 completed 评测）。</p>
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "评测回归门禁结果")
public class GateResult {

    @Schema(description = "评测集ID")
    private Long datasetId;

    @Schema(description = "评测执行记录ID")
    private Long runId;

    @Schema(description = "评测执行UUID")
    private String runUuid;

    @Schema(description = "是否通过门禁")
    private boolean passed;

    @Schema(description = "综合准确率（0-1）")
    private Double accuracy;

    @Schema(description = "P95 延迟（毫秒）")
    private Double latencyP95;

    @Schema(description = "本次 token 成本（美元）")
    private Double tokenCost;

    @Schema(description = "基线评测 UUID")
    private String baselineRunUuid;

    @Schema(description = "基线 token 成本（美元）")
    private Double baselineTokenCost;

    @Schema(description = "各判定项明细")
    private List<GateCriterion> criteria;

    @Schema(description = "门禁结果说明")
    private String message;

    @Schema(description = "扩展信息（门禁结果记录ID等）")
    private Map<String, Object> details;

    @Schema(description = "门禁检查时间")
    private LocalDateTime checkedAt;
}
