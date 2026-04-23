package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import lombok.Builder;
import lombok.Data;

/**
 * Agent 任务详情（含所有 Run 和 Step 时间线）
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "Agent任务详情")
public class AgentTaskDetailDTO {

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

    @Schema(description = "当前活跃run ID")
    private Long currentRunId;

    @Schema(description = "死信原因")
    private String deadLetterReason;

    @Schema(description = "死信时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime deadLetterAt;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;

    @Schema(description = "更新时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime updatedAt;

    @Schema(description = "所有执行记录")
    private List<AgentRunDTO> runs;
}
