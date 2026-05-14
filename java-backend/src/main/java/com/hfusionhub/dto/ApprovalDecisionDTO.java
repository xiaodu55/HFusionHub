package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

/**
 * 审批决策入参 — 替代裸 Map，交由框架层拦截缺失/非法字段。
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "审批决策请求")
public class ApprovalDecisionDTO {

    @NotBlank(message = "approvalId 不能为空")
    @Schema(description = "审批记录 ID")
    private String approvalId;

    @NotBlank(message = "decision 不能为空")
    @Pattern(regexp = "approved|denied", message = "decision 必须为 approved 或 denied")
    @Schema(description = "决策：approved | denied")
    private String decision;

    @Schema(description = "决策原因（拒绝时必须填写）")
    private String reason;
}
