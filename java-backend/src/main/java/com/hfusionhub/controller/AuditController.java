package com.hfusionhub.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.TenantAuditLog;
import com.hfusionhub.mapper.AuditLogMapper;
import com.hfusionhub.mapper.TenantAuditLogMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端审计视图（P3：多租户审计闭环）
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/admin/audit-logs")
@RequiredArgsConstructor
@Tag(name = "审计日志", description = "平台管理员查看操作审计与跨租户代操作审计")
public class AuditController {

    private final AuditLogMapper auditLogMapper;
    private final TenantAuditLogMapper tenantAuditLogMapper;

    @Operation(summary = "操作审计日志", description = "敏感操作（应用/共享/公告等）审计，可按操作人与动作过滤")
    @GetMapping("/operations")
    public R<List<com.hfusionhub.entity.AuditLog>> operations(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(required = false) Long operatorId,
            @RequestParam(required = false) String action) {
        int safeLimit = Math.max(1, Math.min(limit <= 0 ? 50 : limit, 200));
        LambdaQueryWrapper<com.hfusionhub.entity.AuditLog> qw = new LambdaQueryWrapper<>();
        if (operatorId != null) {
            qw.eq(com.hfusionhub.entity.AuditLog::getOperatorId, operatorId);
        }
        if (StringUtils.hasText(action)) {
            qw.like(com.hfusionhub.entity.AuditLog::getAction, action.trim());
        }
        qw.orderByDesc(com.hfusionhub.entity.AuditLog::getId).last("LIMIT " + safeLimit);
        return R.ok(auditLogMapper.selectList(qw));
    }

    @Operation(summary = "跨租户代操作审计", description = "平台管理员跨租户操作的审计记录")
    @GetMapping("/cross-tenant")
    public R<List<TenantAuditLog>> crossTenant(@RequestParam(defaultValue = "50") int limit) {
        int safeLimit = Math.max(1, Math.min(limit <= 0 ? 50 : limit, 200));
        return R.ok(tenantAuditLogMapper.selectList(new LambdaQueryWrapper<TenantAuditLog>()
                .orderByDesc(TenantAuditLog::getId)
                .last("LIMIT " + safeLimit)));
    }
}
