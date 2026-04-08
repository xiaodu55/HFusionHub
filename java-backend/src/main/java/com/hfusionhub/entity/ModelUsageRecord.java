package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 模型调用成本记录（追加式，只插入不更新不删除）
 *
 * <p>与 {@code model_usage_record} 表一一对应。该表没有 deleted / updated_at 列，
 * 因此参照 {@link UsageEvent} 的写法不继承 {@link BaseEntity}，仅保留创建时间填充。</p>
 *
 * @author HFusionHub Team
 */
@Data
@TableName("model_usage_record")
@Schema(description = "模型调用成本记录")
public class ModelUsageRecord {

    @TableId(type = IdType.AUTO)
    @Schema(description = "记录ID")
    private Long id;

    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "会话ID")
    private Long conversationId;

    @Schema(description = "Agent任务ID")
    private Long agentTaskId;

    @Schema(description = "模型名称")
    private String model;

    @Schema(description = "模型提供商")
    private String provider;

    @Schema(description = "输入 tokens")
    private Integer promptTokens;

    @Schema(description = "输出 tokens")
    private Integer completionTokens;

    @Schema(description = "总 tokens")
    private Integer totalTokens;

    @Schema(description = "成本（美元）")
    private BigDecimal costUsd;

    @Schema(description = "延迟（毫秒）")
    private Integer latencyMs;

    @Schema(description = "请求类型: chat|embedding|agent|evaluation")
    private String requestType;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "记录时间")
    private LocalDateTime createdAt;
}
