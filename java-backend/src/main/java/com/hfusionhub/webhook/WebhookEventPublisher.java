package com.hfusionhub.webhook;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

import java.util.Map;

/**
 * Webhook 事件发布器
 *
 * <p>业务模块的对外发布入口：{@code publish(...)} 为同步调用（发布后立即返回），
 * 实际投递由 {@link WebhookDispatcher} 在异步线程完成，不影响主流程耗时。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class WebhookEventPublisher {

    private final ApplicationEventPublisher applicationEventPublisher;

    /**
     * 发布 Webhook 事件
     *
     * @param eventType 事件类型（见 {@link WebhookEventTypes}）
     * @param tenantId  事件归属租户
     * @param userId    事件发起用户（可为 null）
     * @param payload   事件载荷
     */
    public void publish(String eventType, Long tenantId, Long userId, Map<String, Object> payload) {
        if (eventType == null || eventType.isBlank()) {
            log.warn("忽略发布 Webhook 事件：事件类型为空");
            return;
        }
        if (tenantId == null) {
            log.warn("忽略发布 Webhook 事件 {}：缺少租户上下文", eventType);
            return;
        }
        applicationEventPublisher.publishEvent(
                new WebhookEvent(this, eventType, tenantId, userId, payload));
        log.debug("Webhook 事件已发布: type={} tenant={} user={}", eventType, tenantId, userId);
    }
}
