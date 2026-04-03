package com.hfusionhub.service;

import com.hfusionhub.entity.Tenant;
import com.hfusionhub.entity.TenantMember;

import java.util.List;

/**
 * 租户管理服务接口
 *
 * @author HFusionHub Team
 */
public interface TenantService {

    /** 创建租户（平台管理员） */
    Tenant createTenant(String name, String slug, String planTier, Long createdBy);

    /** 根据ID获取租户 */
    Tenant getTenant(Long tenantId);

    /** 根据slug获取租户 */
    Tenant getTenantBySlug(String slug);

    /** 获取用户所属的所有租户 */
    List<Tenant> listUserTenants(Long userId);

    /** 更新租户信息 */
    Tenant updateTenant(Long tenantId, String name, String planTier);

    /** 更新租户状态（active/suspended/deleted） */
    Tenant updateTenantStatus(Long tenantId, String status);

    /** 获取租户成员列表 */
    List<TenantMember> listMembers(Long tenantId);

    /** 添加租户成员 */
    TenantMember addMember(Long tenantId, Long userId, String role);

    /** 更新成员角色 */
    TenantMember updateMemberRole(Long tenantId, Long userId, String newRole);

    /** 移除成员 */
    void removeMember(Long tenantId, Long userId);

    /** 获取成员角色 */
    TenantMember getMemberRole(Long tenantId, Long userId);

    /** 检查用户是否有指定权限 */
    boolean hasPermission(Long userId, String permission);
}
