package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.util.Map;

/** 提示词测试用例 */
@Data
@Builder
@Schema(description = "提示词测试用例")
public class PromptTestCaseDTO {

    @Schema(description = "用例 ID")
    private Long id;

    @Schema(description = "固定问题", example = "如何申请退款？")
    private String question;

    @Schema(description = "模板变量值，如 {\"role\":\"客服\",\"topic\":\"退款\"}")
    private Map<String, Object> variables;

    @Schema(description = "排序号")
    private Integer sortOrder;
}
