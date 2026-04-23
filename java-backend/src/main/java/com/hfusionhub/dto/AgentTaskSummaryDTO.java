package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Data;

/**
 * Agent 任务列表摘要（不含 steps）
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "Agent任务摘要")
public class AgentTaskSummaryDTO {

    @Schema(description = "任务ID")
    private Long id;

    @Schema(description = "客户端幂等键")
    private String requestId;

    @Schema(description = "原始问题（截断）")
    private String query;

    @Schema(description = "知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "任务状态")
    private String status;

    @Schema(description = "是否死信")
    private boolean deadLetter;

    @Schema(description = "死信原因")
    private String deadLetterReason;

    @Schema(description = "总运行次数（含重试）")
    private Integer runCount;

    @Schema(description = "最近错误码")
    private String lastErrorCode;

    @Schema(description = "最近错误信息")
    private String lastErrorMessage;

    @Schema(description = "累计耗时(ms)")
    private Long totalDurationMs;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime updatedAt;
}
