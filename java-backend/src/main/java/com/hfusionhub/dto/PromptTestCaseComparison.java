package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

/** 单个用例在两个运行中的对比 */
@Data
@Builder
@Schema(description = "单个用例在两个运行中的对比")
public class PromptTestCaseComparison {

    @Schema(description = "用例 ID")
    private Long caseId;

    @Schema(description = "用例问题")
    private String question;

    @Schema(description = "左侧运行的结果")
    private PromptTestCaseResult resultA;

    @Schema(description = "右侧运行的结果")
    private PromptTestCaseResult resultB;

    @Schema(description = "回答是否一致（两者均成功时基于内容比较）")
    private Boolean answerIdentical;
}
