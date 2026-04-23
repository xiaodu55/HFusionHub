package com.hfusionhub.webhook;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.entity.WebhookDelivery;
import com.hfusionhub.entity.WebhookSubscription;
import com.hfusionhub.mapper.WebhookDeliveryMapper;
import com.hfusionhub.mapper.WebhookSubscriptionMapper;
import com.hfusionhub.tenant.TenantContext;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

/**
 * Webhook 异步事件分发器
 *
 * <p>监听 {@link WebhookEvent} 应用事件（{@code @Async} 异步），将事件分发给当前
 * 租户下订阅了该事件类型的所有启用订阅，并以 JSON 载荷 POST 到订阅回调地址，
 * 附带 HMAC-SHA256 签名请求头 {@value WebhookSignatureUtils#SIGNATURE_HEADER}。</p>
 *
 * <p>失败重试：指数退避 1m → 5m → 15m，最多 {@value #MAX_RETRIES} 次重试
 * （加上首次投递最多 {@code MAX_RETRIES + 1} 次请求）；订阅连续失败达到
 * {@value #MAX_CONSECUTIVE_FAILURES} 次后自动停用。每次投递尝试均落一条
 * {@code webhook_delivery} 记录。</p>
 *
 * <p>异步线程不继承请求线程的租户上下文，因此所有涉及订阅表的读写均以
 * {@link TenantContext#runAs(Long, Runnable)} 显式声明租户。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class WebhookDispatcher {

    /** 重试退避间隔（毫秒）：1m、5m、15m */
    static final long[] RETRY_DELAYS_MS = {60_000L, 300_000L, 900_000L};

    /** 最大重试次数（首次投递之后，最多再重试 3 次） */
    static final int MAX_RETRIES = 3;

    /** 连续失败次数达到该值自动停用订阅 */
    static final int MAX_CONSECUTIVE_FAILURES = 10;

    /** 响应体 / 错误信息最大落库长度 */
    private static final int BODY_MAX_LENGTH = 2000;

    private final WebhookSubscriptionMapper subscriptionMapper;
    private final WebhookDeliveryMapper deliveryMapper;
    private final ObjectMapper objectMapper;

    @Qualifier("webhookRestTemplate")
    private final RestTemplate restTemplate;

    @Qualifier("webhookRetryScheduler")
    private final ScheduledExecutorService retryScheduler;

    /**
     * 异步监听 Webhook 事件并分发（由 Spring 在 webhookExecutor 线程执行）。
     */
    @Async("webhookExecutor")
    @EventListener
    public void onWebhookEvent(WebhookEvent event) {
        if (event == null) {
            return;
        }
        Long tenantId = event.getTenantId();
        if (tenantId == null) {
            log.warn("Webhook 事件 {} 缺少租户上下文，跳过分发", event.getEventType());
            return;
        }
        try {
            List<WebhookSubscription> subscriptions =
                    TenantContext.runAs(tenantId, () -> subscriptionMapper.selectActiveByEvent(event.getEventType()));
            if (subscriptions.isEmpty()) {
                return;
            }
            log.info("Webhook 事件 {} 匹配到 {} 个订阅", event.getEventType(), subscriptions.size());
            for (WebhookSubscription subscription : subscriptions) {
                deliverWithRetry(subscription, event, 0);
            }
        } catch (Exception e) {
            log.error("Webhook 事件分发失败: event={} tenant={}", event.getEventType(), tenantId, e);
        }
    }

    /**
     * 同步投递一次（不重试）——用于手动测试触发，返回本次投递记录。
     *
     * @param subscription 订阅（须已通过归属校验）
     * @param eventType    事件类型
     * @param payload      载荷
     * @return 投递记录
     */
    public WebhookDelivery deliverSync(
            WebhookSubscription subscription, String eventType, Map<String, Object> payload) {
        Long tenantId = subscription.getTenantId() != null ? subscription.getTenantId() : TenantContext.getTenantId();
        return TenantContext.runAs(tenantId, () -> {
            WebhookDelivery delivery = attempt(subscription, eventType, payload);
            if (delivery.getSuccess() == 1) {
                resetFailureCount(subscription);
            } else {
                incrementFailureCount(subscription);
            }
            return delivery;
        });
    }

    // ================================================================
    // 投递与重试
    // ================================================================

    /**
     * 带重试的投递（递归）。每次失败后按 {@link #RETRY_DELAYS_MS} 指数退避
     * 调度下一次尝试；重试前重新读取订阅，若已被删除/停用则放弃。
     */
    private void deliverWithRetry(WebhookSubscription subscription, WebhookEvent event, int attempt) {
        Long tenantId = subscription.getTenantId() != null ? subscription.getTenantId() : event.getTenantId();
        TenantContext.runAs(tenantId, () -> {
            WebhookDelivery delivery = attempt(subscription, event.getEventType(), event.getPayload());
            if (delivery.getSuccess() == 1) {
                resetFailureCount(subscription);
                return null;
            }
            WebhookSubscription updated = incrementFailureCount(subscription);
            if (updated == null || !Integer.valueOf(1).equals(updated.getIsActive())) {
                log.warn("Webhook 订阅 {} 已停用，停止重试事件 {}", subscription.getId(), event.getEventType());
                return null;
            }
            if (attempt + 1 >= MAX_RETRIES) {
                log.warn(
                        "Webhook 订阅 {} 事件 {} 经 {} 次尝试仍失败，放弃投递",
                        subscription.getId(),
                        event.getEventType(),
                        attempt + 1);
                return null;
            }
            long delayMs = RETRY_DELAYS_MS[attempt];
            log.info(
                    "Webhook 订阅 {} 事件 {} 第 {} 次投递失败，{}ms 后重试",
                    subscription.getId(),
                    event.getEventType(),
                    attempt + 1,
                    delayMs);
            retryScheduler.schedule(
                    () -> {
                        try {
                            TenantContext.runAs(tenantId, () -> {
                                WebhookSubscription current = subscriptionMapper.selectById(subscription.getId());
                                if (current == null || !Integer.valueOf(1).equals(current.getIsActive())) {
                                    log.warn("Webhook 订阅 {} 在重试前已被删除或停用，放弃重试", subscription.getId());
                                    return null;
                                }
                                deliverWithRetry(current, event, attempt + 1);
                                return null;
                            });
                        } catch (Exception e) {
                            log.error("Webhook 重试执行异常: sub={} event={}", subscription.getId(), event.getEventType(), e);
                        }
                    },
                    delayMs,
                    TimeUnit.MILLISECONDS);
            return null;
        });
    }

    /**
     * 执行一次 HTTP 投递并落投递记录（单次，不含重试逻辑）。
     */
    private WebhookDelivery attempt(WebhookSubscription subscription, String eventType, Map<String, Object> payload) {
        long start = System.currentTimeMillis();
        String payloadJson = toJson(payload);

        WebhookDelivery delivery = new WebhookDelivery();
        delivery.setSubscriptionId(subscription.getId());
        delivery.setEventType(eventType);
        delivery.setPayload(payloadJson);
        delivery.setSuccess(0);
        delivery.setResponseStatus(0);
        delivery.setDurationMs(0);

        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.set(WebhookSignatureUtils.EVENT_HEADER, eventType);
            String signature = WebhookSignatureUtils.sign(subscription.getSecret(), payloadJson);
            if (signature != null) {
                headers.set(WebhookSignatureUtils.SIGNATURE_HEADER, signature);
            }

            ResponseEntity<String> response = restTemplate.postForEntity(
                    subscription.getUrl(), new HttpEntity<>(payloadJson, headers), String.class);
            delivery.setResponseStatus(response.getStatusCode().value());
            delivery.setResponseBody(truncate(response.getBody(), BODY_MAX_LENGTH));
            delivery.setSuccess(response.getStatusCode().is2xxSuccessful() ? 1 : 0);
            if (delivery.getSuccess() != 1) {
                log.warn(
                        "Webhook 投递返回非 2xx: sub={} status={}",
                        subscription.getId(),
                        response.getStatusCode().value());
            }
        } catch (RestClientException e) {
            delivery.setResponseStatus(0);
            delivery.setResponseBody(truncate(e.getMessage(), BODY_MAX_LENGTH));
            log.warn(
                    "Webhook 投递网络异常: sub={} url={} error={}",
                    subscription.getId(),
                    subscription.getUrl(),
                    e.getMessage());
        } finally {
            delivery.setDurationMs((int) (System.currentTimeMillis() - start));
            try {
                deliveryMapper.insert(delivery);
            } catch (Exception e) {
                log.error("Webhook 投递记录落库失败: sub={}", subscription.getId(), e);
            }
            touchLastTriggered(subscription);
        }
        return delivery;
    }

    // ================================================================
    // 订阅状态维护
    // ================================================================

    /** 更新订阅的最近触发时间 */
    private void touchLastTriggered(WebhookSubscription subscription) {
        try {
            subscriptionMapper.update(
                    null,
                    new LambdaUpdateWrapper<WebhookSubscription>()
                            .eq(WebhookSubscription::getId, subscription.getId())
                            .set(WebhookSubscription::getLastTriggeredAt, LocalDateTime.now()));
        } catch (Exception e) {
            log.warn("更新订阅触发时间失败: sub={}", subscription.getId(), e);
        }
    }

    /** 成功投递后清零连续失败计数 */
    private void resetFailureCount(WebhookSubscription subscription) {
        if (subscription.getFailureCount() == null || subscription.getFailureCount() == 0) {
            return;
        }
        subscriptionMapper.update(
                null,
                new LambdaUpdateWrapper<WebhookSubscription>()
                        .eq(WebhookSubscription::getId, subscription.getId())
                        .set(WebhookSubscription::getFailureCount, 0));
    }

    /**
     * 连续失败计数 +1；达到 {@value #MAX_CONSECUTIVE_FAILURES} 次自动停用订阅。
     *
     * @return 更新后的订阅（null 表示订阅已不存在）
     */
    private WebhookSubscription incrementFailureCount(WebhookSubscription subscription) {
        subscriptionMapper.update(
                null,
                new LambdaUpdateWrapper<WebhookSubscription>()
                        .eq(WebhookSubscription::getId, subscription.getId())
                        .setSql("failure_count = failure_count + 1"));
        WebhookSubscription updated = subscriptionMapper.selectById(subscription.getId());
        if (updated != null
                && updated.getFailureCount() != null
                && updated.getFailureCount() >= MAX_CONSECUTIVE_FAILURES) {
            updated.setIsActive(0);
            subscriptionMapper.updateById(updated);
            log.warn("Webhook 订阅 {} 连续失败 {} 次，已自动停用", updated.getId(), updated.getFailureCount());
        }
        return updated;
    }

    // ================================================================
    // 辅助
    // ================================================================

    private String toJson(Map<String, Object> payload) {
        try {
            return objectMapper.writeValueAsString(payload != null ? payload : Map.of());
        } catch (JsonProcessingException e) {
            log.warn("Webhook 载荷序列化失败，回退为简单 JSON: {}", e.getMessage());
            return "{}";
        }
    }

    private static String truncate(String value, int maxLength) {
        if (value == null) {
            return null;
        }
        return value.length() > maxLength ? value.substring(0, maxLength) : value;
    }
}
