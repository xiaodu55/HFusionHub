package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * Agent 恢复审计事件实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName("agent_recovery_event")
@Schema(description = "Agent恢复审计事件")
public class AgentRecoveryEvent {

    /**
     * 事件ID
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "事件ID")
    private Long id;

    /**
     * 运行ID
     */
    @Schema(description = "运行ID")
    private Long runId;

    /**
     * 任务ID
     */
    @Schema(description = "任务ID")
    private Long taskId;

    /**
     * 事件类型：ORPHAN_RECLAIMED|WATCHDOG_TIMED_OUT|SUPERSEDED_REJECTED|STALE_CALLBACK_REJECTED|DEAD_LETTERED|RESTART_RECOVERED
     */
    @Schema(description = "事件类型")
    private String eventType;

    /**
     * 恢复详情
     */
    @Schema(description = "恢复详情")
    private String detail;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
