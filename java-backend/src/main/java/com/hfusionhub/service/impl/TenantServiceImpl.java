package com.hfusionhub.service.impl;

import com.hfusionhub.entity.Tenant;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.mapper.RolePermissionMapper;
import com.hfusionhub.mapper.TenantMapper;
import com.hfusionhub.mapper.TenantMemberMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.TenantService;
import java.util.List;
import java.util.NoSuchElementException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 租户管理服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TenantServiceImpl implements TenantService {

    private final TenantMapper tenantMapper;
    private final TenantMemberMapper tenantMemberMapper;
    private final RolePermissionMapper rolePermissionMapper;
    private final UserMapper userMapper;

    @Override
    @Transactional
    public Tenant createTenant(String name, String slug, String planTier, Long createdBy) {
        Tenant existing = tenantMapper.selectBySlug(slug);
        if (existing != null) {
            throw new IllegalArgumentException("租户标识已存在: " + slug);
        }

        Tenant tenant = new Tenant();
        tenant.setName(name);
        tenant.setSlug(slug);
        tenant.setPlanTier(planTier != null ? planTier : "free");
        tenant.setStatus("active");
        tenant.setCreatedBy(createdBy);
        tenantMapper.insert(tenant);

        log.info("租户创建成功: {} (slug={}, plan={})", tenant.getId(), slug, planTier);
        return tenant;
    }

    @Override
    public Tenant getTenant(Long tenantId) {
        Tenant tenant = tenantMapper.selectById(tenantId);
        if (tenant == null) {
            throw new NoSuchElementException("租户不存在: " + tenantId);
        }
        return tenant;
    }

    @Override
    public Tenant getTenantBySlug(String slug) {
        return tenantMapper.selectBySlug(slug);
    }

    @Override
    public List<Tenant> listUserTenants(Long userId) {
        return tenantMapper.selectByUserId(userId);
    }

    @Override
    @Transactional
    public Tenant updateTenant(Long tenantId, String name, String planTier) {
        Tenant tenant = getTenant(tenantId);
        if (StringUtils.hasText(name)) {
            tenant.setName(name);
        }
        if (StringUtils.hasText(planTier)) {
            tenant.setPlanTier(planTier);
        }
        tenantMapper.updateById(tenant);
        return tenant;
    }

    @Override
    @Transactional
    public Tenant updateTenantStatus(Long tenantId, String status) {
        Tenant tenant = getTenant(tenantId);
        tenant.setStatus(status);
        tenantMapper.updateById(tenant);
        log.info("租户状态更新: {} -> {}", tenantId, status);
        return tenant;
    }

    @Override
    public List<TenantMember> listMembers(Long tenantId) {
        return tenantMemberMapper.selectByTenantId(tenantId);
    }

    @Override
    @Transactional
    public TenantMember addMember(Long tenantId, Long userId, String role) {
        // Check not already a member
        TenantMember existing = tenantMemberMapper.selectByTenantAndUser(tenantId, userId);
        if (existing != null) {
            throw new IllegalStateException("用户已是该租户成员");
        }

        TenantMember member = new TenantMember();
        member.setTenantId(tenantId);
        member.setUserId(userId);
        member.setRole(role != null ? role : "member");
        tenantMemberMapper.insert(member);

        log.info("租户成员添加: tenant={} user={} role={}", tenantId, userId, role);
        return member;
    }

    @Override
    @Transactional
    public TenantMember updateMemberRole(Long tenantId, Long userId, String newRole) {
        TenantMember member = requireMember(tenantId, userId);
        member.setRole(newRole);
        tenantMemberMapper.updateById(member);
        log.info("成员角色更新: tenant={} user={} role={}", tenantId, userId, newRole);
        return member;
    }

    @Override
    @Transactional
    public void removeMember(Long tenantId, Long userId) {
        TenantMember member = requireMember(tenantId, userId);
        tenantMemberMapper.deleteById(member.getId());
        log.info("租户成员移除: tenant={} user={}", tenantId, userId);
    }

    @Override
    public TenantMember getMemberRole(Long tenantId, Long userId) {
        return tenantMemberMapper.selectByTenantAndUser(tenantId, userId);
    }

    @Override
    public boolean hasPermission(Long userId, String permission) {
        var user = userMapper.selectById(userId);
        if (user == null) return false;

        // Platform admin can do anything
        if (Boolean.TRUE.equals(user.getPlatformAdmin())) return true;

        // Check tenant member role permissions
        if (user.getTenantId() != null) {
            var member = tenantMemberMapper.selectByTenantAndUser(user.getTenantId(), userId);
            if (member != null) {
                List<String> perms = rolePermissionMapper.selectPermissionsByRole(member.getRole());
                return perms.contains(permission) || perms.contains("*");
            }
        }
        return false;
    }

    private TenantMember requireMember(Long tenantId, Long userId) {
        TenantMember member = tenantMemberMapper.selectByTenantAndUser(tenantId, userId);
        if (member == null) {
            throw new NoSuchElementException("成员不存在: tenant=" + tenantId + " user=" + userId);
        }
        return member;
    }

    @Override
    public boolean isMemberOfTenant(Long tenantId, Long userId) {
        return tenantMemberMapper.selectByTenantAndUser(tenantId, userId) != null;
    }

    @Override
    public boolean isTenantAdmin(Long tenantId, Long userId) {
        TenantMember member = tenantMemberMapper.selectByTenantAndUser(tenantId, userId);
        return member != null && "admin".equals(member.getRole());
    }
}
