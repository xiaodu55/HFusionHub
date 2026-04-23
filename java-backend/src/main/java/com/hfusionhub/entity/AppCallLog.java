package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 应用调用记录（含按 Key 计费）
 *
 * @author HFusionHub Team
 */
@Data
@TableName("app_call_log")
@Schema(description = "应用调用记录")
public class AppCallLog {

    @TableId(type = IdType.AUTO)
    @Schema(description = "记录ID")
    private Long id;

    @Schema(description = "FK → app.id")
    private Long appId;

    @Schema(description = "FK → app_api_key.id")
    private Long apiKeyId;

    @Schema(description = "调用方用户（内部调用时）")
    private Long userId;

    @Schema(description = "租户")
    private Long tenantId;

    @Schema(description = "ok | error | rate_limited")
    private String status;

    @Schema(description = "Prompt tokens")
    private Integer promptTokens;

    @Schema(description = "Completion tokens")
    private Integer completionTokens;

    @Schema(description = "总 tokens")
    private Integer totalTokens;

    @Schema(description = "调用时间")
    private LocalDateTime createdAt;
}
