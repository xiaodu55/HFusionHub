package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.PlanBindingDTO;
import com.hfusionhub.entity.BidSubscription;
import com.hfusionhub.service.BidPlanGateService;
import com.hfusionhub.service.BidSubscriptionService;
import com.hfusionhub.service.TenantPlanBindingService;
import com.hfusionhub.tenant.TenantContext;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.HashMap;
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
 * 投标套餐控制器（招投标垂直化 · P2 商业化）
 *
 * <p>套餐目录选购 + 租户套餐绑定；平台管理员可维护套餐。绑定 tier 套餐时同步
 * {@code tenant.plan_tier} 与既有每日限额引擎对齐。</p>
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/bid/plan")
@RequiredArgsConstructor
@Tag(name = "投标套餐", description = "订阅套餐目录与租户套餐绑定（P2 商业化）")
public class BidPlanController {

    private final BidSubscriptionService subscriptionService;
    private final TenantPlanBindingService bindingService;
    private final BidPlanGateService gateService;

    @GetMapping("/catalog")
    @Operation(summary = "平台内置套餐目录", description = "供租户选购（含基础档位与行业方案包）")
    public R<List<BidSubscription>> catalog() {
        return R.ok(subscriptionService.listPlatformPlans());
    }

    @GetMapping("/current")
    @Operation(summary = "当前租户套餐概览", description = "基础档位 + 模块生效状态（套餐授权∩平台开关）+ 有效绑定列表")
    public R<Map<String, Object>> current() {
        Long tenantId = TenantContext.requireTenantId();
        Map<String, Object> result = new HashMap<>();
        result.put("tier", bindingService.resolveCurrentTier(tenantId));
        result.put("modules", gateService.moduleStatus(tenantId));
        result.put("bindings", bindingService.listActiveBindings(tenantId));
        return R.ok(result);
    }

    @PostMapping("/bind")
    @Operation(summary = "绑定套餐", description = "当前租户绑定；tier 套餐同步 tenant.plan_tier")
    public R<PlanBindingDTO> bind(@RequestParam Long subscriptionId) {
        return R.ok("套餐已绑定", bindingService.bind(subscriptionId));
    }

    @PostMapping("/unbind")
    @Operation(summary = "解绑套餐", description = "当前租户解绑（置为 canceled）")
    public R<Void> unbind(@RequestParam Long subscriptionId) {
        bindingService.unbind(subscriptionId);
        return R.ok("套餐已解绑", null);
    }

    // ── 平台管理员 ─────────────────────────────────────────────

    @GetMapping("/admin")
    @SaCheckRole("admin")
    @Operation(summary = "全量套餐（管理员）", description = "含归档与租户自定义套餐")
    public R<List<BidSubscription>> listAll() {
        return R.ok(subscriptionService.listAll());
    }

    @PostMapping("/admin")
    @SaCheckRole("admin")
    @Operation(summary = "新建套餐（管理员）")
    public R<BidSubscription> create(@RequestBody BidSubscription subscription) {
        return R.ok("套餐已创建", subscriptionService.create(subscription));
    }

    @PutMapping("/admin")
    @SaCheckRole("admin")
    @Operation(summary = "更新套餐（管理员）")
    public R<Void> update(@RequestBody BidSubscription subscription) {
        subscriptionService.update(subscription);
        return R.ok("套餐已更新", null);
    }

    @DeleteMapping("/admin/{id}")
    @SaCheckRole("admin")
    @Operation(summary = "归档套餐（管理员）", description = "不再可选，历史绑定不受影响")
    public R<Void> archive(@PathVariable Long id) {
        subscriptionService.archive(id);
        return R.ok("套餐已归档", null);
    }
}
