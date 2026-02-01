package com.hfusionhub.common.utils;

import cn.dev33.satoken.stp.StpInterface;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.common.constant.CommonConstants;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * JWT 工具类（基于 Sa-Token）
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class JwtUtils implements StpInterface {

    /**
     * 返回一个账号所拥有的权限码集合
     *
     * @param loginId  账号id
     * @param loginType 账号类型
     * @return 权限码集合
     */
    @Override
    public List<String> getPermissionList(Object loginId, String loginType) {
        // 这里可以查询数据库获取用户权限
        // 暂时返回空列表
        return List.of();
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
        // 这里可以查询数据库获取用户角色
        // 暂时返回普通用户角色
        return List.of(CommonConstants.ROLE_USER);
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
     * 登出
     */
    public static void logout() {
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
     * 获取当前登录用户ID（字符串）
     *
     * @return 用户ID
     */
    public static String getCurrentUserIdStr() {
        return StpUtil.getLoginIdAsString();
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
