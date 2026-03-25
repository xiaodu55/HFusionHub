package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.util.List;

/** 两个批量运行记录的逐用例对比结果 */
@Data
@Builder
@Schema(description = "两个批量运行记录的逐用例对比结果")
public class PromptTestSetCompareResponse {

    @Schema(description = "左侧运行信息")
    private PromptTestSetRunDTO runA;

    @Schema(description = "右侧运行信息")
    private PromptTestSetRunDTO runB;

    @Schema(description = "逐用例对比（按用例顺序）")
    private List<PromptTestCaseComparison> comparisons;

    @Schema(description = "对比的用例数")
    private int comparedCases;
}
