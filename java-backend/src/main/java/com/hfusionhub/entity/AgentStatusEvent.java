package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.hfusionhub.handler.JsonMapTypeHandler;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.Map;
import lombok.Data;

/**
 * Agent 状态事件实体 — SSE 推送与审计
 *
 * @author HFusionHub Team
 */
@Data
@TableName("agent_status_event")
@Schema(description = "Agent状态事件")
public class AgentStatusEvent {

    /**
     * 事件ID（单调递增，SSE断点续传）
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "事件ID")
    private Long id;

    /**
     * 任务ID
     */
    @Schema(description = "任务ID")
    private Long taskId;

    /**
     * 运行ID（可能为空）
     */
    @Schema(description = "运行ID")
    private Long runId;

    /**
     * 事件类型：QUEUED|RUN_STARTED|STEP_RECORDED|RETRY_SCHEDULED|RUN_SUCCEEDED|RUN_FAILED|RUN_TIMED_OUT|CANCELLED|DEAD_LETTERED|RECOVERED|APPROVAL_REQUIRED|APPROVAL_DECIDED
     */
    @Schema(description = "事件类型")
    private String eventType;

    /**
     * 事件发生时任务状态
     */
    @Schema(description = "任务状态")
    private String status;

    /**
     * 附加载荷（错误码/尝试次数/下次重试时间等）
     */
    @TableField(typeHandler = JsonMapTypeHandler.class)
    @Schema(description = "附加载荷")
    private Map<String, Object> payload;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
