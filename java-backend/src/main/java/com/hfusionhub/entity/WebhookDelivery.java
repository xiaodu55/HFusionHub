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
 * Webhook 投递记录实体（追加式，每次投递尝试一行）
 *
 * <p>表无 tenant_id / deleted 列，参照 {@link UsageEvent} 的写法不继承
 * {@link BaseEntity}；已登记在租户行拦截器的忽略表中。</p>
 *
 * @author HFusionHub Team
 */
@Data
@TableName("webhook_delivery")
@Schema(description = "Webhook 投递记录")
public class WebhookDelivery {

    @TableId(type = IdType.AUTO)
    @Schema(description = "投递记录ID")
    private Long id;

    @Schema(description = "订阅ID")
    private Long subscriptionId;

    @Schema(description = "事件类型")
    private String eventType;

    @Schema(description = "请求体（JSON 字符串）")
    private String payload;

    @Schema(description = "响应状态码（网络异常时为 0）")
    private Integer responseStatus;

    @Schema(description = "响应体（截断存储）")
    private String responseBody;

    @Schema(description = "投递耗时（毫秒）")
    private Integer durationMs;

    @Schema(description = "是否成功：1-成功，0-失败")
    private Integer success;

    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "投递时间")
    private LocalDateTime createdAt;
}
