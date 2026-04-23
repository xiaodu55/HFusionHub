package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Data;

/** 提示词测试用例集（列表项） */
@Data
@Builder
@Schema(description = "提示词测试用例集（列表项）")
public class PromptTestSetDTO {

    @Schema(description = "用例集 ID")
    private Long id;

    @Schema(description = "用例集名称")
    private String name;

    @Schema(description = "用例集描述")
    private String description;

    @Schema(description = "用例数量")
    private Long caseCount;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
