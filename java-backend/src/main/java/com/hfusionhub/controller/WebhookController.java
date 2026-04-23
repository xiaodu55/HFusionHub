package com.hfusionhub.controller;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.WebhookDelivery;
import com.hfusionhub.entity.WebhookSubscription;
import com.hfusionhub.service.WebhookSubscriptionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Webhook 订阅管理控制器
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/webhook")
@RequiredArgsConstructor
@Tag(name = "Webhook", description = "Webhook 订阅管理与投递")
public class WebhookController {

    private final WebhookSubscriptionService subscriptionService;

    @GetMapping
    @Operation(summary = "当前用户的 Webhook 订阅列表")
    public R<List<WebhookSubscription>> list() {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(subscriptionService.listByUser(userId));
    }

    @PostMapping
    @Operation(summary = "创建 Webhook 订阅")
    public R<WebhookSubscription> create(@RequestBody WebhookSubscription subscription) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok("订阅创建成功", subscriptionService.create(userId, subscription));
    }

    @GetMapping("/{id}")
    @Operation(summary = "获取订阅详情")
    public R<WebhookSubscription> get(@PathVariable Long id) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(subscriptionService.get(userId, id));
    }

    @PutMapping("/{id}")
    @Operation(summary = "更新订阅（名称/地址/密钥/事件）")
    public R<WebhookSubscription> update(@PathVariable Long id, @RequestBody WebhookSubscription subscription) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(subscriptionService.update(userId, id, subscription));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除订阅")
    public R<Void> delete(@PathVariable Long id) {
        Long userId = JwtUtils.getCurrentUserId();
        subscriptionService.delete(userId, id);
        return R.ok();
    }

    @PutMapping("/{id}/active")
    @Operation(summary = "启停订阅")
    public R<WebhookSubscription> setActive(@PathVariable Long id, @RequestBody Map<String, Object> body) {
        Long userId = JwtUtils.getCurrentUserId();
        boolean active = Boolean.TRUE.equals(body.get("active"));
        return R.ok(subscriptionService.setActive(userId, id, active));
    }

    @PostMapping("/{id}/test")
    @Operation(summary = "测试触发一次投递（同步）")
    public R<WebhookDelivery> testFire(@PathVariable Long id) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(subscriptionService.testFire(userId, id));
    }

    @GetMapping("/{id}/deliveries")
    @Operation(summary = "投递历史（分页）")
    public R<PageResult<WebhookDelivery>> deliveries(
            @PathVariable Long id,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(subscriptionService.deliveryHistory(userId, id, page, pageSize));
    }
}
