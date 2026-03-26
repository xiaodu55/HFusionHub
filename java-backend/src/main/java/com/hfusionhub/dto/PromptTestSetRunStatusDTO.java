package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

/** 批量运行任务的实时状态（排队/进度/终态），供前端轮询展示。 */
@Data
@Builder
@Schema(description = "批量运行任务的实时状态")
public class PromptTestSetRunStatusDTO {

    @Schema(description = "运行记录 ID")
    private Long id;

    @Schema(description = "用例集 ID")
    private Long setId;

    @Schema(description = "任务状态：pending|running|succeeded|failed|cancelled")
    private String status;

    @Schema(description = "重试次数")
    private int attemptNumber;

    @Schema(description = "已完成用例数")
    private int progressCount;

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

    @Schema(description = "终态失败原因")
    private String errorMessage;

    @Schema(description = "排队时间")
    private LocalDateTime scheduledAt;

    @Schema(description = "开始执行时间")
    private LocalDateTime startedAt;

    @Schema(description = "结束时间")
    private LocalDateTime completedAt;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
