package com.hfusionhub.service;

import com.hfusionhub.dto.UserInfoDTO;
import com.hfusionhub.dto.UserLoginDTO;
import com.hfusionhub.dto.UserRegisterDTO;
import com.hfusionhub.dto.UserUpdateDTO;

/**
 * 用户服务接口
 *
 * @author HFusionHub Team
 */
public interface UserService {

    /**
     * 用户登录
     *
     * @param loginDTO 登录请求
     * @return Token
     */
    String login(UserLoginDTO loginDTO);

    /**
     * 用户注册
     *
     * @param registerDTO 注册请求
     * @return 用户信息
     */
    UserInfoDTO register(UserRegisterDTO registerDTO);

    /**
     * 用户登出
     */
    void logout();

    /**
     * 获取当前用户信息
     *
     * @return 用户信息
     */
    UserInfoDTO getCurrentUser();

    /**
     * 更新用户信息
     *
     * @param updateDTO 更新请求
     * @return 用户信息
     */
    UserInfoDTO updateUser(UserUpdateDTO updateDTO);

    /**
     * 根据用户ID获取用户信息
     *
     * @param userId 用户ID
     * @return 用户信息
     */
    UserInfoDTO getUserById(Long userId);

    /**
     * 根据用户名获取用户信息
     *
     * @param username 用户名
     * @return 用户信息
     */
    UserInfoDTO getUserByUsername(String username);
}
