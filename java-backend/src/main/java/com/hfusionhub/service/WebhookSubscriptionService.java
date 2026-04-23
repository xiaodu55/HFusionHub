package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.entity.WebhookDelivery;
import com.hfusionhub.entity.WebhookSubscription;
import java.util.List;

/**
 * Webhook 订阅管理服务
 *
 * @author HFusionHub Team
 */
public interface WebhookSubscriptionService {

    /**
     * 创建订阅
     *
     * @param userId 当前用户ID
     * @param sub    订阅信息（name / url / events 必填，secret 为空时自动生成）
     * @return 创建的订阅
     */
    WebhookSubscription create(Long userId, WebhookSubscription sub);

    /**
     * 更新订阅（仅本人）
     *
     * @param userId 当前用户ID
     * @param id     订阅ID
     * @param sub    更新的字段
     * @return 更新后的订阅
     */
    WebhookSubscription update(Long userId, Long id, WebhookSubscription sub);

    /**
     * 删除订阅（逻辑删除，仅本人）
     *
     * @param userId 当前用户ID
     * @param id     订阅ID
     */
    void delete(Long userId, Long id);

    /**
     * 获取订阅详情（仅本人）
     *
     * @param userId 当前用户ID
     * @param id     订阅ID
     * @return 订阅
     */
    WebhookSubscription get(Long userId, Long id);

    /**
     * 当前用户的订阅列表
     *
     * @param userId 当前用户ID
     * @return 订阅列表（按创建时间倒序）
     */
    List<WebhookSubscription> listByUser(Long userId);

    /**
     * 启停订阅（仅本人）
     *
     * @param userId 当前用户ID
     * @param id     订阅ID
     * @param active 是否启用
     * @return 更新后的订阅
     */
    WebhookSubscription setActive(Long userId, Long id, boolean active);

    /**
     * 手动测试触发一次投递（同步执行，不重试）
     *
     * @param userId 当前用户ID
     * @param id     订阅ID
     * @return 本次投递记录
     */
    WebhookDelivery testFire(Long userId, Long id);

    /**
     * 订阅的投递历史（分页，仅本人）
     *
     * @param userId         当前用户ID
     * @param subscriptionId 订阅ID
     * @param page           页码（从 1 开始）
     * @param pageSize       每页条数（1-100）
     * @return 分页投递记录（按时间倒序）
     */
    PageResult<WebhookDelivery> deliveryHistory(Long userId, Long subscriptionId, int page, int pageSize);
}
