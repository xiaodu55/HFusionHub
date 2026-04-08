package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.User;
import com.hfusionhub.entity.WebhookDelivery;
import com.hfusionhub.entity.WebhookSubscription;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.mapper.WebhookDeliveryMapper;
import com.hfusionhub.mapper.WebhookSubscriptionMapper;
import com.hfusionhub.service.WebhookSubscriptionService;
import com.hfusionhub.webhook.WebhookDispatcher;
import com.hfusionhub.webhook.WebhookEventTypes;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.security.SecureRandom;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Webhook 订阅管理服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class WebhookSubscriptionServiceImpl implements WebhookSubscriptionService {

    private final WebhookSubscriptionMapper subscriptionMapper;
    private final WebhookDeliveryMapper deliveryMapper;
    private final UserMapper userMapper;
    private final WebhookDispatcher webhookDispatcher;

    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    /** 已知事件类型全集（用于创建/更新时的校验） */
    private static final Set<String> KNOWN_EVENTS = Set.of(
            WebhookEventTypes.AGENT_TASK_COMPLETED,
            WebhookEventTypes.AGENT_TASK_FAILED,
            WebhookEventTypes.AGENT_APPROVAL_REQUIRED,
            WebhookEventTypes.DOCUMENT_INDEXED,
            WebhookEventTypes.EVALUATION_COMPLETED
    );

    @Override
    @Transactional
    public WebhookSubscription create(Long userId, WebhookSubscription sub) {
        validatePayload(sub);

        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException("用户不存在");
        }
        WebhookSubscription entity = new WebhookSubscription();
        entity.setUserId(userId);
        entity.setTenantId(user.getTenantId());
        entity.setName(sub.getName().trim());
        entity.setUrl(sub.getUrl().trim());
        entity.setSecret(StringUtils.hasText(sub.getSecret()) ? sub.getSecret() : generateSecret());
        entity.setEvents(sub.getEvents());
        entity.setIsActive(1);
        entity.setFailureCount(0);
        subscriptionMapper.insert(entity);

        log.info("Webhook 订阅创建成功: id={} user={} events={}",
                entity.getId(), userId, entity.getEvents());
        return entity;
    }

    @Override
    @Transactional
    public WebhookSubscription update(Long userId, Long id, WebhookSubscription sub) {
        WebhookSubscription existing = get(userId, id);
        if (StringUtils.hasText(sub.getName())) {
            existing.setName(sub.getName().trim());
        }
        if (StringUtils.hasText(sub.getUrl())) {
            validateUrl(sub.getUrl());
            existing.setUrl(sub.getUrl().trim());
        }
        if (sub.getSecret() != null && !sub.getSecret().isBlank()) {
            existing.setSecret(sub.getSecret());
        }
        if (sub.getEvents() != null && !sub.getEvents().isEmpty()) {
            validateEvents(sub.getEvents());
            existing.setEvents(sub.getEvents());
        }
        subscriptionMapper.updateById(existing);
        log.info("Webhook 订阅更新成功: id={}", id);
        return existing;
    }

    @Override
    @Transactional
    public void delete(Long userId, Long id) {
        WebhookSubscription existing = get(userId, id);
        subscriptionMapper.deleteById(existing.getId());
        log.info("Webhook 订阅删除成功: id={}", id);
    }

    @Override
    public WebhookSubscription get(Long userId, Long id) {
        WebhookSubscription sub = subscriptionMapper.selectById(id);
        if (sub == null) {
            throw new BusinessException("Webhook 订阅不存在: " + id);
        }
        if (!userId.equals(sub.getUserId())) {
            throw new BusinessException("无权访问该 Webhook 订阅");
        }
        return sub;
    }

    @Override
    public List<WebhookSubscription> listByUser(Long userId) {
        LambdaQueryWrapper<WebhookSubscription> query = new LambdaQueryWrapper<>();
        query.eq(WebhookSubscription::getUserId, userId)
             .orderByDesc(WebhookSubscription::getCreatedAt);
        return subscriptionMapper.selectList(query);
    }

    @Override
    @Transactional
    public WebhookSubscription setActive(Long userId, Long id, boolean active) {
        WebhookSubscription existing = get(userId, id);
        existing.setIsActive(active ? 1 : 0);
        subscriptionMapper.updateById(existing);
        log.info("Webhook 订阅状态更新: id={} active={}", id, active);
        return existing;
    }

    @Override
    public WebhookDelivery testFire(Long userId, Long id) {
        WebhookSubscription sub = get(userId, id);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("event", "test");
        payload.put("subscription_id", sub.getId());
        payload.put("subscription_name", sub.getName());
        payload.put("timestamp", System.currentTimeMillis());
        return webhookDispatcher.deliverSync(sub, "test", payload);
    }

    @Override
    public PageResult<WebhookDelivery> deliveryHistory(Long userId, Long subscriptionId,
                                                       int page, int pageSize) {
        get(userId, subscriptionId);
        page = Math.max(1, page);
        pageSize = Math.max(1, Math.min(pageSize, 100));
        int offset = (page - 1) * pageSize;

        LambdaQueryWrapper<WebhookDelivery> query = new LambdaQueryWrapper<>();
        query.eq(WebhookDelivery::getSubscriptionId, subscriptionId)
             .orderByDesc(WebhookDelivery::getCreatedAt)
             .orderByDesc(WebhookDelivery::getId)
             .last("LIMIT " + offset + "," + pageSize);
        List<WebhookDelivery> records = deliveryMapper.selectList(query);

        long total = deliveryMapper.selectCount(
                new LambdaQueryWrapper<WebhookDelivery>()
                        .eq(WebhookDelivery::getSubscriptionId, subscriptionId));
        return PageResult.of(page, pageSize, total, records);
    }

    // ================================================================
    // 内部辅助
    // ================================================================

    private void validatePayload(WebhookSubscription sub) {
        if (!StringUtils.hasText(sub.getName())) {
            throw new BusinessException("订阅名称不能为空");
        }
        if (!StringUtils.hasText(sub.getUrl())) {
            throw new BusinessException("回调地址不能为空");
        }
        validateUrl(sub.getUrl());
        if (sub.getEvents() == null || sub.getEvents().isEmpty()) {
            throw new BusinessException("至少订阅一个事件类型");
        }
        validateEvents(sub.getEvents());
    }

    private void validateUrl(String url) {
        String trimmed = url.trim().toLowerCase();
        if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
            throw new BusinessException("回调地址必须以 http:// 或 https:// 开头");
        }
    }

    private void validateEvents(List<String> events) {
        Set<String> eventSet = new HashSet<>(events);
        for (String event : eventSet) {
            if (!KNOWN_EVENTS.contains(event)) {
                throw new BusinessException("不支持的事件类型: " + event
                        + "（支持: " + String.join(", ", KNOWN_EVENTS) + "）");
            }
        }
    }

    /** 生成随机订阅密钥（32 位十六进制） */
    private static String generateSecret() {
        byte[] bytes = new byte[16];
        SECURE_RANDOM.nextBytes(bytes);
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }
}
