package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

/** 提示词测试用例集详情（含用例列表） */
@Data
@Builder
@Schema(description = "提示词测试用例集详情（含用例列表）")
public class PromptTestSetDetailDTO {

    @Schema(description = "用例集 ID")
    private Long id;

    @Schema(description = "用例集名称")
    private String name;

    @Schema(description = "用例集描述")
    private String description;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;

    @Schema(description = "用例列表")
    private List<PromptTestCaseDTO> cases;
}
