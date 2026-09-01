package com.hfusionhub.common.utils;

import cn.dev33.satoken.stp.StpInterface;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.UserMapper;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * JWT 工具类（基于 Sa-Token）
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class JwtUtils implements StpInterface {

    private final UserMapper userMapper;

    /**
     * 返回一个账号所拥有的权限码集合
     *
     * @param loginId  账号id
     * @param loginType 账号类型
     * @return 权限码集合
     */
    @Override
    public List<String> getPermissionList(Object loginId, String loginType) {
        try {
            Long userId = Long.parseLong(loginId.toString());
            User user = userMapper.selectById(userId);
            if (user == null) return List.of();

            // Platform admin gets all permissions
            if (Boolean.TRUE.equals(user.getPlatformAdmin())) {
                return List.of("*");
            }

            // Tenant-scoped permissions based on member role
            if (user.getTenantId() != null) {
                // Load tenant member role and its permissions
                var member = getUserTenantMember(user);
                if (member != null && member.getRole() != null) {
                    List<String> perms = getPermissionsForRole(member.getRole());
                    if (!perms.isEmpty()) return perms;
                }
            }
        } catch (Exception e) {
            log.warn("获取用户权限失败: loginId={}", loginId, e);
        }
        return List.of();
    }

    private TenantMember getUserTenantMember(User user) {
        try {
            var mapper = SpringContextHolder.getBean(com.hfusionhub.mapper.TenantMemberMapper.class);
            return mapper.selectByTenantAndUser(user.getTenantId(), user.getId());
        } catch (Exception e) {
            return null;
        }
    }

    private List<String> getPermissionsForRole(String role) {
        try {
            var mapper = SpringContextHolder.getBean(com.hfusionhub.mapper.RolePermissionMapper.class);
            return mapper.selectPermissionsByRole(role);
        } catch (Exception e) {
            return List.of();
        }
    }

    /**
     * 返回一个账号所拥有的角色标识集合
     *
     * @param loginId  账号id
     * @param loginType 账号类型
     * @return 角色标识集合
     */
    @Override
    public List<String> getRoleList(Object loginId, String loginType) {
        // 从数据库加载用户真实角色
        try {
            Long userId = Long.parseLong(loginId.toString());
            User user = userMapper.selectById(userId);
            if (user != null && user.getRole() != null) {
                return List.of(user.getRole());
            }
        } catch (Exception e) {
            log.warn("获取用户角色失败: loginId={}", loginId, e);
        }
        // Fail closed when the account cannot be loaded. Never grant a business role by default.
        return List.of();
    }

    /**
     * 登录
     *
     * @param userId 用户ID
     */
    public static void login(Long userId) {
        StpUtil.login(userId);
        log.info("用户登录成功，userId: {}", userId);
    }

    /**
     * 登出（UserServiceImpl 账户注销路径在用）
     */
    public void logout() {
        StpUtil.logout();
        log.info("用户登出成功");
    }

    /**
     * 获取当前登录用户ID
     *
     * @return 用户ID
     */
    public static Long getCurrentUserId() {
        return StpUtil.getLoginIdAsLong();
    }

    /**
     * 判断是否已登录
     *
     * @return 是否已登录
     */
    public static boolean isLogin() {
        return StpUtil.isLogin();
    }

    /**
     * 获取当前登录用户的 Token 值
     *
     * @return Token 值
     */
    public static String getTokenValue() {
        return StpUtil.getTokenValue();
    }

    /**
     * 校验当前账号是否具有指定角色
     *
     * @param role 角色标识
     * @return 是否具有该角色
     */
    public static boolean hasRole(String role) {
        return StpUtil.hasRole(role);
    }

    /**
     * 校验当前账号是否具有指定权限
     *
     * @param permission 权限标识
     * @return 是否具有该权限
     */
    public static boolean hasPermission(String permission) {
        return StpUtil.hasPermission(permission);
    }
}
