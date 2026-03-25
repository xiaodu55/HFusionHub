package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/** 对比两个批量运行记录的请求 */
@Data
@Schema(description = "对比两个批量运行记录的请求")
public class PromptTestSetCompareRequest {

    @NotNull(message = "左侧运行记录 ID 不能为空")
    @Schema(description = "左侧运行记录 ID")
    private Long runIdA;

    @NotNull(message = "右侧运行记录 ID 不能为空")
    @Schema(description = "右侧运行记录 ID")
    private Long runIdB;
}
