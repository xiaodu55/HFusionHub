package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.service.TenantService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

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

    @GetMapping
    @Operation(summary = "获取租户成员列表")
    public R<List<TenantMember>> listMembers(@PathVariable Long tenantId) {
        return R.ok(tenantService.listMembers(tenantId));
    }

    @PostMapping
    @Operation(summary = "添加租户成员")
    public R<TenantMember> addMember(@PathVariable Long tenantId,
                                     @RequestBody Map<String, Object> body) {
        Long userId = Long.valueOf(body.get("userId").toString());
        String role = (String) body.getOrDefault("role", "member");
        return R.ok(tenantService.addMember(tenantId, userId, role));
    }

    @PutMapping("/{userId}")
    @Operation(summary = "更新成员角色")
    public R<TenantMember> updateRole(@PathVariable Long tenantId,
                                      @PathVariable Long userId,
                                      @RequestBody Map<String, String> body) {
        return R.ok(tenantService.updateMemberRole(tenantId, userId, body.get("role")));
    }

    @DeleteMapping("/{userId}")
    @Operation(summary = "移除成员")
    public R<Void> removeMember(@PathVariable Long tenantId,
                                @PathVariable Long userId) {
        tenantService.removeMember(tenantId, userId);
        return R.ok();
    }
}
