package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.util.List;

/** 批量运行测试用例集的整体响应 */
@Data
@Builder
@Schema(description = "批量运行测试用例集的整体响应")
public class PromptTestSetRunResponse {

    @Schema(description = "用例集 ID")
    private Long setId;

    @Schema(description = "用例总数")
    private int totalCases;

    @Schema(description = "成功数")
    private int successCount;

    @Schema(description = "失败数")
    private int failureCount;

    @Schema(description = "总耗时（毫秒）")
    private long totalElapsedMs;

    @Schema(description = "各用例运行结果（顺序与用例排序一致）")
    private List<PromptTestCaseResult> results;
}
