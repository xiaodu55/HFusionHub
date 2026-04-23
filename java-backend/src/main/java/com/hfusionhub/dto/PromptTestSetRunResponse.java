package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import lombok.Builder;
import lombok.Data;

/** 批量运行测试用例集的整体响应 */
@Data
@Builder
@Schema(description = "批量运行测试用例集的整体响应")
public class PromptTestSetRunResponse {

    @Schema(description = "用例集 ID")
    private Long setId;

    @Schema(description = "本次运行记录 ID（用于历史与对比）")
    private Long runId;

    @Schema(description = "任务状态（completed 时为 succeeded）")
    private String status;

    @Schema(description = "来源模板 ID（可选）")
    private Long templateId;

    @Schema(description = "来源模板版本号（可选）")
    private Integer templateVersion;

    @Schema(description = "来源模板名称（可选）")
    private String templateName;

    @Schema(description = "用例总数")
    private int totalCases;

    @Schema(description = "成功数")
    private int successCount;

    @Schema(description = "失败数")
    private int failureCount;

    @Schema(description = "通过数（满足通过规则的用例数）")
    private int passCount;

    @Schema(description = "通过率（0-100，保留一位小数）")
    private double passRate;

    @Schema(description = "总耗时（毫秒）")
    private long totalElapsedMs;

    @Schema(description = "各用例运行结果（顺序与用例排序一致）")
    private List<PromptTestCaseResult> results;
}
