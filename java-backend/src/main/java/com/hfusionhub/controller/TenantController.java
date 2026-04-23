package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.Tenant;
import com.hfusionhub.service.TenantService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 租户管理控制器
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/tenant")
@RequiredArgsConstructor
@Tag(name = "租户管理", description = "租户与组织管理")
public class TenantController {

    private final TenantService tenantService;

    @PostMapping
    @Operation(summary = "创建租户（平台管理员）")
    @SaCheckRole("admin")
    public R<Tenant> create(@RequestBody Map<String, String> body) {
        Tenant tenant = tenantService.createTenant(
                body.get("name"), body.get("slug"), body.getOrDefault("planTier", "free"), JwtUtils.getCurrentUserId());
        return R.ok("租户创建成功", tenant);
    }

    @GetMapping("/my")
    @Operation(summary = "获取当前用户的租户列表")
    public R<List<Tenant>> myTenants() {
        List<Tenant> tenants = tenantService.listUserTenants(JwtUtils.getCurrentUserId());
        return R.ok(tenants);
    }

    @GetMapping("/{tenantId}")
    @Operation(summary = "获取租户详情")
    public R<Tenant> getTenant(@PathVariable Long tenantId) {
        return R.ok(tenantService.getTenant(tenantId));
    }

    @PutMapping("/{tenantId}")
    @Operation(summary = "更新租户信息")
    @SaCheckRole("admin")
    public R<Tenant> update(@PathVariable Long tenantId, @RequestBody Map<String, String> body) {
        return R.ok(tenantService.updateTenant(tenantId, body.get("name"), body.get("planTier")));
    }

    @PutMapping("/{tenantId}/status")
    @Operation(summary = "更新租户状态（suspend/restore）")
    @SaCheckRole("admin")
    public R<Tenant> updateStatus(@PathVariable Long tenantId, @RequestBody Map<String, String> body) {
        return R.ok(tenantService.updateTenantStatus(tenantId, body.get("status")));
    }
}
