package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Data;

/**
 * Agent 任务完整状态 DTO（任务摘要 + 活跃 Run 调度信息 + 最新事件）
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "Agent任务完整状态")
public class AgentTaskStatusDTO {

    @Schema(description = "任务ID")
    private Long id;

    @Schema(description = "客户端幂等键")
    private String requestId;

    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "对话ID")
    private Long conversationId;

    @Schema(description = "知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "原始问题")
    private String query;

    @Schema(description = "任务状态")
    private String status;

    @Schema(description = "是否死信")
    private boolean deadLetter;

    @Schema(description = "死信原因")
    private String deadLetterReason;

    @Schema(description = "当前活跃Run ID")
    private Long currentRunId;

    @Schema(description = "当前Run状态")
    private String currentRunStatus;

    @Schema(description = "当前Run计划执行时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime currentRunScheduledAt;

    @Schema(description = "当前Run尝试次数")
    private Integer currentRunAttemptNumber;

    @Schema(description = "总Run数")
    private Integer totalRunCount;

    @Schema(description = "最新事件")
    private AgentStatusEventDTO latestEvent;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime updatedAt;
}
