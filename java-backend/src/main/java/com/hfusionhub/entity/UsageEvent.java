package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 用量账本事件（不可变，只插入不更新不删除）
 *
 * <p>唯一键 (request_id, operation) 保证同一业务请求的 RESERVE / COMMIT / RELEASE
 * 各只落账一次，用于端到端幂等。</p>
 *
 * @author HFusionHub Team
 */
@Data
@TableName("usage_event")
@Schema(description = "用量账本事件")
public class UsageEvent {

    @TableId(type = IdType.AUTO)
    @Schema(description = "事件ID")
    private Long id;

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "计量项: chat_tokens|agent_tokens|index_chunks|plugin_executions")
    private String meter;

    @Schema(description = "账本操作: RESERVE|COMMIT|RELEASE")
    private String operation;

    @Schema(description = "业务幂等键")
    private String requestId;

    @Schema(description = "UTC 日窗口 YYYY-MM-DD")
    private String windowKey;

    @Schema(description = "本次金额")
    private Long amount;

    @Schema(description = "引用类型: message|document_index|agent_run|plugin_execution")
    private String refType;

    @Schema(description = "引用ID")
    private String refId;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
