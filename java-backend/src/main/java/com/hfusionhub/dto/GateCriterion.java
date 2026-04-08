package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 评测门禁单项判定
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "评测门禁单项判定")
public class GateCriterion {

    /** 判定项名称 */
    @Schema(description = "判定项: accuracy|latency_p95|token_cost")
    private String name;

    @Schema(description = "判定项说明")
    private String description;

    /** 判定状态: PASSED | FAILED | SKIPPED（SKIPPED 表示上游未上报该指标，不参与门禁判定） */
    @Schema(description = "判定状态: PASSED|FAILED|SKIPPED")
    private String status;

    @Schema(description = "实际值（展示用）")
    private String actual;

    @Schema(description = "阈值（展示用）")
    private String threshold;

    @Schema(description = "补充说明")
    private String detail;
}
