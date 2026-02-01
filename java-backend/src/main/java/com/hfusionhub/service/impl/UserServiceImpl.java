package com.hfusionhub.service.impl;

import cn.hutool.crypto.digest.BCrypt;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.UserInfoDTO;
import com.hfusionhub.dto.UserLoginDTO;
import com.hfusionhub.dto.UserRegisterDTO;
import com.hfusionhub.dto.UserUpdateDTO;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.UserService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

/**
 * 用户服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class UserServiceImpl implements UserService {

    private final UserMapper userMapper;
    private final JwtUtils jwtUtils;

    /**
     * 用户登录
     *
     * @param loginDTO 登录请求
     * @return Token
     */
    @Override
    public String login(UserLoginDTO loginDTO) {
        // 根据用户名查询用户
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(User::getUsername, loginDTO.getUsername());
        User user = userMapper.selectOne(wrapper);

        // 校验用户是否存在
        if (user == null) {
            throw new BusinessException(StatusCode.LOGIN_ERROR, "用户名或密码错误");
        }

        // 校验用户状态
        if (user.getStatus() == 1) {
            throw new BusinessException(StatusCode.USER_DISABLED, "用户已被禁用");
        }

        // 校验密码
        if (!BCrypt.checkpw(loginDTO.getPassword(), user.getPassword())) {
            throw new BusinessException(StatusCode.LOGIN_ERROR, "用户名或密码错误");
        }

        // 更新最后登录时间
        user.setLastLoginTime(LocalDateTime.now());
        userMapper.updateById(user);

        // 登录
        jwtUtils.login(user.getId());

        log.info("用户登录成功，userId: {}, username: {}", user.getId(), user.getUsername());
        return jwtUtils.getTokenValue();
    }

    /**
     * 用户注册
     *
     * @param registerDTO 注册请求
     * @return 用户信息
     */
    @Override
    public UserInfoDTO register(UserRegisterDTO registerDTO) {
        // 检查用户名是否已存在
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(User::getUsername, registerDTO.getUsername());
        Long count = userMapper.selectCount(wrapper);
        if (count > 0) {
            throw new BusinessException(StatusCode.USER_EXISTS, "用户名已存在");
        }

        // 检查邮箱是否已存在（如果填写了邮箱）
        if (registerDTO.getEmail() != null && !registerDTO.getEmail().isEmpty()) {
            LambdaQueryWrapper<User> emailWrapper = new LambdaQueryWrapper<>();
            emailWrapper.eq(User::getEmail, registerDTO.getEmail());
            Long emailCount = userMapper.selectCount(emailWrapper);
            if (emailCount > 0) {
                throw new BusinessException(StatusCode.USER_EXISTS, "邮箱已被注册");
            }
        }

        // 创建用户
        User user = new User();
        user.setUsername(registerDTO.getUsername());
        user.setPassword(BCrypt.hashpw(registerDTO.getPassword()));
        user.setNickname(registerDTO.getNickname());
        user.setEmail(registerDTO.getEmail());
        user.setPhone(registerDTO.getPhone());
        user.setRole("user");
        user.setStatus(0);

        userMapper.insert(user);

        log.info("用户注册成功，userId: {}, username: {}", user.getId(), user.getUsername());
        return convertToUserInfoDTO(user);
    }

    /**
     * 用户登出
     */
    @Override
    public void logout() {
        jwtUtils.logout();
        log.info("用户登出成功");
    }

    /**
     * 获取当前用户信息
     *
     * @return 用户信息
     */
    @Override
    public UserInfoDTO getCurrentUser() {
        Long userId = jwtUtils.getCurrentUserId();
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "用户不存在");
        }
        return convertToUserInfoDTO(user);
    }

    /**
     * 更新用户信息
     *
     * @param updateDTO 更新请求
     * @return 用户信息
     */
    @Override
    public UserInfoDTO updateUser(UserUpdateDTO updateDTO) {
        Long userId = jwtUtils.getCurrentUserId();
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "用户不存在");
        }

        // 更新字段（只更新非空字段）
        if (updateDTO.getNickname() != null) {
            user.setNickname(updateDTO.getNickname());
        }
        if (updateDTO.getEmail() != null) {
            // 检查邮箱是否已被其他用户使用
            LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
            wrapper.eq(User::getEmail, updateDTO.getEmail())
                    .ne(User::getId, userId);
            Long count = userMapper.selectCount(wrapper);
            if (count > 0) {
                throw new BusinessException(StatusCode.USER_EXISTS, "邮箱已被其他用户使用");
            }
            user.setEmail(updateDTO.getEmail());
        }
        if (updateDTO.getPhone() != null) {
            user.setPhone(updateDTO.getPhone());
        }
        if (updateDTO.getAvatar() != null) {
            user.setAvatar(updateDTO.getAvatar());
        }

        userMapper.updateById(user);

        log.info("用户信息更新成功，userId: {}", userId);
        return convertToUserInfoDTO(user);
    }

    /**
     * 根据用户ID获取用户信息
     *
     * @param userId 用户ID
     * @return 用户信息
     */
    @Override
    public UserInfoDTO getUserById(Long userId) {
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "用户不存在");
        }
        return convertToUserInfoDTO(user);
    }

    /**
     * 根据用户名获取用户信息
     *
     * @param username 用户名
     * @return 用户信息
     */
    @Override
    public UserInfoDTO getUserByUsername(String username) {
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(User::getUsername, username);
        User user = userMapper.selectOne(wrapper);
        if (user == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "用户不存在");
        }
        return convertToUserInfoDTO(user);
    }

    /**
     * User 实体转换为 UserInfoDTO
     *
     * @param user 用户实体
     * @return 用户信息DTO
     */
    private UserInfoDTO convertToUserInfoDTO(User user) {
        return UserInfoDTO.builder()
                .id(user.getId())
                .username(user.getUsername())
                .nickname(user.getNickname())
                .email(user.getEmail())
                .phone(user.getPhone())
                .avatar(user.getAvatar())
                .role(user.getRole())
                .status(user.getStatus())
                .lastLoginTime(user.getLastLoginTime())
                .createdAt(user.getCreatedAt())
                .build();
    }
}
