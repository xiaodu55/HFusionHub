package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

/** 单次批量运行历史记录（列表项） */
@Data
@Builder
@Schema(description = "单次批量运行历史记录")
public class PromptTestSetRunDTO {

    @Schema(description = "运行记录 ID")
    private Long id;

    @Schema(description = "来源模板 ID（可选）")
    private Long templateId;

    @Schema(description = "来源模板版本号（可选）")
    private Integer templateVersion;

    @Schema(description = "来源模板名称（可选）")
    private String templateName;

    @Schema(description = "实际执行/保存的模板内容快照（绑定模板时为数据库真实内容）")
    private String templateContent;

    @Schema(description = "关联知识库 ID（可选）")
    private Long knowledgeBaseId;

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

    @Schema(description = "任务状态：pending|running|succeeded|failed|cancelled")
    private String status;

    @Schema(description = "重试次数")
    private int attemptNumber;

    @Schema(description = "已完成用例数")
    private int progressCount;

    @Schema(description = "终态失败原因")
    private String errorMessage;

    @Schema(description = "开始执行时间")
    private LocalDateTime startedAt;

    @Schema(description = "结束时间")
    private LocalDateTime completedAt;

    @Schema(description = "运行时间")
    private LocalDateTime createdAt;
}
