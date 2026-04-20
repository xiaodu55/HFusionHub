package com.hfusionhub.service.impl;

import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.AuditLog;
import com.hfusionhub.mapper.AuditLogMapper;
import com.hfusionhub.service.AuditLogService;
import com.hfusionhub.tenant.TenantContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

/**
 * 操作审计服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AuditLogServiceImpl implements AuditLogService {

    private final AuditLogMapper auditLogMapper;

    @Override
    public void record(String action, String targetType, String targetId, String detail) {
        try {
            AuditLog entry = new AuditLog();
            entry.setOperatorId(JwtUtils.getCurrentUserId());
            entry.setTenantId(TenantContext.getTenantId() == null ? 1L : TenantContext.getTenantId());
            entry.setAction(action);
            entry.setTargetType(targetType);
            entry.setTargetId(targetId);
            entry.setDetail(detail == null || detail.length() <= 500 ? detail : detail.substring(0, 500));
            entry.setCreatedAt(LocalDateTime.now());
            auditLogMapper.insert(entry);
        } catch (Exception e) {
            // 审计失败不应阻断主流程
            log.warn("审计记录写入失败: action={}, err={}", action, e.getMessage());
        }
    }
}
