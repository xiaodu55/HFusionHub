package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.hfusionhub.handler.JsonListTypeHandler;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Webhook 订阅配置实体
 *
 * <p>表含 deleted / updated_at 列，继承 {@link BaseEntity} 获得创建时间、更新时间和
 * 逻辑删除（@TableLogic）能力；events 列以 JSON 数组存储订阅的事件类型。</p>
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName(value = "webhook_subscription", autoResultMap = true)
@Schema(description = "Webhook 订阅配置")
public class WebhookSubscription extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "订阅ID")
    private Long id;

    @Schema(description = "创建者用户ID")
    private Long userId;

    @Schema(description = "租户ID")
    private Long tenantId;

    @Schema(description = "订阅名称")
    private String name;

    @Schema(description = "回调 URL")
    private String url;

    @Schema(description = "签名密钥（HMAC-SHA256，可为空则不签名）")
    private String secret;

    @TableField(typeHandler = JsonListTypeHandler.class)
    @Schema(description = "订阅的事件类型列表（JSON 数组）")
    private List<String> events;

    @TableField("is_active")
    @Schema(description = "是否启用：1-启用，0-停用")
    private Integer isActive;

    @Schema(description = "最近一次触发时间")
    private LocalDateTime lastTriggeredAt;

    @Schema(description = "连续失败次数（>=10 自动停用）")
    private Integer failureCount;
}
