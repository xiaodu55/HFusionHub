package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * Agent 任务实体 — 每次用户请求一条记录
 *
 * @author HFusionHub Team
 */
@Data
@TableName("agent_task")
@Schema(description = "Agent任务实体")
public class AgentTask {

    /**
     * 任务ID
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "任务ID")
    private Long id;

    /**
     * 客户端幂等键（唯一约束）
     */
    @Schema(description = "客户端幂等键")
    private String requestId;

    /**
     * 用户ID
     */
    @Schema(description = "用户ID")
    private Long userId;

    /**
     * 对话ID
     */
    @Schema(description = "对话ID")
    private Long conversationId;

    /**
     * 知识库ID（可选）
     */
    @Schema(description = "知识库ID")
    private Long knowledgeBaseId;

    /**
     * 原始问题
     */
    @Schema(description = "原始问题")
    private String query;

    /**
     * 状态：pending|running|waiting_approval|succeeded|failed|cancelled|timed_out
     */
    @Schema(description = "任务状态")
    private String status;

    /**
     * 当前活跃 run 的 ID
     */
    @Schema(description = "当前活跃run ID")
    private Long currentRunId;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;
}
