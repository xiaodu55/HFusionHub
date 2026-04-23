package com.hfusionhub.controller;

import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.service.TenantService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Map;
import java.util.Set;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 租户成员管理控制器
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/tenant/{tenantId}/member")
@RequiredArgsConstructor
@Tag(name = "租户成员管理", description = "租户成员增删改查")
public class TenantMemberController {

    private final TenantService tenantService;

    private static final Set<String> ALLOWED_ROLES = Set.of("admin", "member", "viewer");

    /**
     * 校验调用者是目标租户成员（或平台管理员）。
     */
    private void requireTenantMembership(Long tenantId) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        if (JwtUtils.hasRole(CommonConstants.ROLE_ADMIN)) return;
        if (!tenantService.isMemberOfTenant(tenantId, currentUserId)) {
            throw new BusinessException(StatusCode.FORBIDDEN, "无权访问该租户");
        }
    }

    /**
     * 校验调用者是目标租户管理员（或平台管理员）。
     */
    private void requireTenantAdmin(Long tenantId) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        if (JwtUtils.hasRole(CommonConstants.ROLE_ADMIN)) return;
        if (!tenantService.isTenantAdmin(tenantId, currentUserId)) {
            throw new BusinessException(StatusCode.FORBIDDEN, "仅租户管理员可执行此操作");
        }
    }

    @GetMapping
    @Operation(summary = "获取租户成员列表")
    public R<List<TenantMember>> listMembers(@PathVariable Long tenantId) {
        requireTenantMembership(tenantId);
        return R.ok(tenantService.listMembers(tenantId));
    }

    @PostMapping
    @Operation(summary = "添加租户成员")
    public R<TenantMember> addMember(@PathVariable Long tenantId, @RequestBody Map<String, Object> body) {
        requireTenantAdmin(tenantId);
        Long userId = Long.valueOf(body.get("userId").toString());
        String role = (String) body.getOrDefault("role", "member");
        if (!ALLOWED_ROLES.contains(role)) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "无效的角色: " + role + "，允许值: " + ALLOWED_ROLES);
        }
        return R.ok(tenantService.addMember(tenantId, userId, role));
    }

    @PutMapping("/{userId}")
    @Operation(summary = "更新成员角色")
    public R<TenantMember> updateRole(
            @PathVariable Long tenantId, @PathVariable Long userId, @RequestBody Map<String, String> body) {
        requireTenantAdmin(tenantId);
        String role = body.get("role");
        if (role == null || !ALLOWED_ROLES.contains(role)) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "无效的角色: " + role + "，允许值: " + ALLOWED_ROLES);
        }
        return R.ok(tenantService.updateMemberRole(tenantId, userId, role));
    }

    @DeleteMapping("/{userId}")
    @Operation(summary = "移除成员")
    public R<Void> removeMember(@PathVariable Long tenantId, @PathVariable Long userId) {
        requireTenantAdmin(tenantId);
        tenantService.removeMember(tenantId, userId);
        return R.ok();
    }
}
