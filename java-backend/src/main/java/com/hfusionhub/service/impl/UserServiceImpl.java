package com.hfusionhub.service.impl;

import cn.hutool.crypto.digest.BCrypt;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.limiter.LoginRateLimiter;
import com.hfusionhub.common.utils.IpUtils;
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
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.time.LocalDateTime;
import java.util.Locale;

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
    private final LoginRateLimiter rateLimiter;

    @Value("${app.trusted-proxy-headers:false}")
    private boolean trustedProxyHeaders;

    /**
     * 用户登录
     *
     * @param loginDTO 登录请求
     * @return Token
     */
    @Override
    public String login(UserLoginDTO loginDTO) {
        String ip = getClientIp();
        String username = loginDTO.getUsername();

        // 根据用户名查询用户
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(User::getUsername, username);
        User user = userMapper.selectOne(wrapper);

        // 校验用户是否存在
        if (user == null) {
            rateLimiter.recordFailedAttempt(ip);
            log.warn("AUTH_LOGIN_FAILED user={} ip={} reason=user_not_found", username, ip);
            throw new BusinessException(StatusCode.LOGIN_ERROR, "用户名或密码错误");
        }

        // 校验用户状态
        if (user.getStatus() == 1) {
            log.warn("AUTH_LOGIN_FAILED user={} ip={} reason=user_disabled", username, ip);
            throw new BusinessException(StatusCode.USER_DISABLED, "用户已被禁用");
        }

        // 校验密码
        if (!BCrypt.checkpw(loginDTO.getPassword(), user.getPassword())) {
            rateLimiter.recordFailedAttempt(ip);
            log.warn("AUTH_LOGIN_FAILED user={} ip={} reason=bad_password", username, ip);
            throw new BusinessException(StatusCode.LOGIN_ERROR, "用户名或密码错误");
        }

        // 更新最后登录时间
        user.setLastLoginTime(LocalDateTime.now());
        userMapper.updateById(user);

        // 登录成功 — 清除失败计数
        rateLimiter.recordSuccess(ip);

        jwtUtils.login(user.getId());

        log.info("AUTH_LOGIN_SUCCESS userId={} username={} ip={}", user.getId(), username, ip);
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
        String username = trimToNull(registerDTO.getUsername());
        String email = normaliseEmail(registerDTO.getEmail());
        String phone = trimToNull(registerDTO.getPhone());
        String nickname = trimToNull(registerDTO.getNickname());

        // 检查用户名是否已存在
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(User::getUsername, username);
        Long count = userMapper.selectCount(wrapper);
        if (count > 0) {
            throw new BusinessException(StatusCode.USER_EXISTS, "用户名已存在");
        }

        // 检查邮箱是否已存在（如果填写了邮箱）
        if (email != null) {
            LambdaQueryWrapper<User> emailWrapper = new LambdaQueryWrapper<>();
            emailWrapper.eq(User::getEmail, email);
            Long emailCount = userMapper.selectCount(emailWrapper);
            if (emailCount > 0) {
                throw new BusinessException(StatusCode.USER_EXISTS, "邮箱已被注册");
            }
        }

        // 创建用户
        User user = new User();
        user.setUsername(username);
        user.setPassword(BCrypt.hashpw(registerDTO.getPassword()));
        user.setNickname(nickname != null ? nickname : username);
        user.setEmail(email);
        user.setPhone(phone);
        user.setRole("user");
        user.setStatus(0);

        try {
            userMapper.insert(user);
        } catch (DuplicateKeyException e) {
            // The pre-check improves feedback, while the database unique index
            // remains the authoritative guard against concurrent registration.
            log.info("AUTH_REGISTER_CONFLICT username={} email={}", username, email);
            throw new BusinessException(StatusCode.USER_EXISTS, "用户名或邮箱已被注册");
        }

        String ip = getClientIp();
        log.info("AUTH_REGISTER_SUCCESS userId={} username={} ip={}", user.getId(), user.getUsername(), ip);
        return convertToUserInfoDTO(user);
    }

    private String normaliseEmail(String email) {
        String normalised = trimToNull(email);
        return normalised == null ? null : normalised.toLowerCase(Locale.ROOT);
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
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
     * 根据用户ID获取用户信息（管理员或本人）
     *
     * @param userId 用户ID
     * @return 用户信息
     */
    @Override
    public UserInfoDTO getUserById(Long userId) {
        // 权限校验：管理员可查看任意用户，普通用户只能查看自己
        Long currentUserId = JwtUtils.getCurrentUserId();
        if (!JwtUtils.hasRole(CommonConstants.ROLE_ADMIN) && !currentUserId.equals(userId)) {
            throw new BusinessException(StatusCode.FORBIDDEN, "无权查看其他用户信息");
        }
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
     * Extract client IP from the current HTTP request context.
     */
    private String getClientIp() {
        try {
            ServletRequestAttributes attrs =
                    (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();
            return IpUtils.getClientIp(attrs.getRequest(), trustedProxyHeaders);
        } catch (IllegalStateException e) {
            return "unknown";
        }
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
