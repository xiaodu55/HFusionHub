package com.hfusionhub.webhook;

import java.util.Map;
import lombok.Getter;
import org.springframework.context.ApplicationEvent;

/**
 * Webhook 应用事件
 *
 * <p>业务模块通过 {@link ApplicationEventPublisher}（推荐经由
 * {@link WebhookEventPublisher#publish(String, Long, Long, Map)}）发布，
 * 由 {@link WebhookDispatcher} 异步监听并按订阅分发。</p>
 *
 * @author HFusionHub Team
 */
@Getter
public class WebhookEvent extends ApplicationEvent {

    private static final long serialVersionUID = 1L;

    /** 事件类型，取值见 {@link WebhookEventTypes} */
    private final String eventType;

    /** 事件归属租户（决定订阅查询的租户隔离上下文） */
    private final Long tenantId;

    /** 事件发起用户（可为 null） */
    private final Long userId;

    /** 事件载荷（将被序列化为投递请求体 JSON） */
    private final Map<String, Object> payload;

    /**
     * 构造 Webhook 事件
     *
     * @param source    事件源
     * @param eventType 事件类型
     * @param tenantId  租户ID
     * @param userId    用户ID（可为 null）
     * @param payload   载荷
     */
    public WebhookEvent(Object source, String eventType, Long tenantId, Long userId, Map<String, Object> payload) {
        super(source);
        this.eventType = eventType;
        this.tenantId = tenantId;
        this.userId = userId;
        this.payload = payload;
    }
}
