package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import lombok.Builder;
import lombok.Data;

/** 单次批量运行的详情：运行信息 + 每个用例的结果 */
@Data
@Builder
@Schema(description = "单次批量运行的详情")
public class PromptTestSetRunDetailDTO {

    @Schema(description = "运行信息")
    private PromptTestSetRunDTO run;

    @Schema(description = "各用例结果")
    private List<PromptTestCaseResult> results;
}
