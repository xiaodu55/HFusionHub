package com.hfusionhub.service.impl;

import cn.hutool.crypto.digest.BCrypt;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.limiter.LoginRateLimiter;
import com.hfusionhub.common.utils.IpUtils;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.AdminPasswordResetDTO;
import com.hfusionhub.dto.PasswordChangeDTO;
import com.hfusionhub.dto.UserInfoDTO;
import com.hfusionhub.dto.UserLoginDTO;
import com.hfusionhub.dto.UserRegisterDTO;
import com.hfusionhub.dto.UserSearchDTO;
import com.hfusionhub.dto.UserUpdateDTO;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.TenantMemberMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.UserService;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/**
 * 用户服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class UserServiceImpl implements UserService {

    private static final Set<String> ALLOWED_PLATFORM_ROLES = Set.of(
            CommonConstants.ROLE_PENDING,
            CommonConstants.ROLE_USER,
            CommonConstants.ROLE_BUILDER,
            CommonConstants.ROLE_ADMIN);

    private static final Set<String> ASSIGNABLE_PLATFORM_ROLES =
            Set.of(CommonConstants.ROLE_PENDING, CommonConstants.ROLE_USER, CommonConstants.ROLE_BUILDER);

    /** 头像大小上限 2MB */
    private static final long AVATAR_MAX_SIZE = 2 * 1024 * 1024L;
    /** DB avatar 字段存储的标准相对路径标记（实际落盘目录由 {@link #avatarDir} 决定） */
    private static final String AVATAR_DB_PREFIX = "uploads/avatars/";
    /**
     * 头像落盘目录（相对应用工作目录，与文档上传 uploads/ 同卷持久化；
     * 可配置以便测试注入临时目录）
     */
    @Value("${app.avatar.dir:uploads/avatars}")
    private String avatarDir;
    /** 允许的图片类型：扩展名 → Content-Type → 魔数 */
    private static final Map<String, String> AVATAR_TYPES = Map.of(
            "jpg", "image/jpeg",
            "jpeg", "image/jpeg",
            "png", "image/png",
            "webp", "image/webp",
            "gif", "image/gif");

    private final UserMapper userMapper;
    private final TenantMemberMapper tenantMemberMapper;
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

        // 登录防爆破：IP 已达失败阈值（5 次/15 分钟）则直接拒绝（HTTP 429）
        rateLimiter.checkBlocked(ip);

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
    @Transactional
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
        user.setRole(CommonConstants.ROLE_PENDING);
        user.setStatus(CommonConstants.USER_STATUS_NORMAL);
        user.setTenantId(CommonConstants.DEFAULT_TENANT_ID);

        try {
            userMapper.insert(user);
            TenantMember member = new TenantMember();
            member.setTenantId(CommonConstants.DEFAULT_TENANT_ID);
            member.setUserId(user.getId());
            member.setRole("member");
            tenantMemberMapper.insert(member);
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
     * 修改当前用户密码
     *
     * @param dto 旧密码 + 新密码
     */
    @Override
    public void changePassword(PasswordChangeDTO dto) {
        Long userId = jwtUtils.getCurrentUserId();
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "用户不存在");
        }
        if (user.getPassword() == null || !BCrypt.checkpw(dto.getOldPassword(), user.getPassword())) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "当前密码不正确");
        }
        if (dto.getOldPassword().equals(dto.getNewPassword())) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "新密码不能与当前密码相同");
        }
        User update = new User();
        update.setId(userId);
        update.setPassword(BCrypt.hashpw(dto.getNewPassword()));
        userMapper.updateById(update);
    }

    /**
     * 管理员重置用户密码（忘记密码场景；无需旧密码）
     *
     * @param userId 目标用户 ID
     * @param dto 临时新密码
     * @return 更新后的用户信息
     */
    @Override
    public UserInfoDTO resetUserPassword(Long userId, AdminPasswordResetDTO dto) {
        Long operatorId = jwtUtils.getCurrentUserId();
        if (operatorId != null && operatorId.equals(userId)) {
            // 自己的密码走 changePassword（需旧密码），避免绕过本人验证
            throw new BusinessException(StatusCode.BAD_REQUEST, "不能通过管理员重置修改自己的密码，请使用「修改密码」");
        }
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "用户不存在");
        }
        User update = new User();
        update.setId(userId);
        update.setPassword(BCrypt.hashpw(dto.getNewPassword()));
        userMapper.updateById(update);
        log.info("管理员 {} 重置了用户 {} 的密码", operatorId, userId);
        return convertToUserInfoDTO(userMapper.selectById(userId));
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
            wrapper.eq(User::getEmail, updateDTO.getEmail()).ne(User::getId, userId);
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
        if (updateDTO.getThemePreference() != null) {
            user.setThemePreference(updateDTO.getThemePreference());
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

    @Override
    public PageResult<UserInfoDTO> listUsers(long page, long pageSize, String keyword, String role) {
        long safePage = Math.max(page, 1);
        long safePageSize = Math.min(Math.max(pageSize, 1), 100);
        String normalizedKeyword = trimToNull(keyword);
        String normalizedRole = trimToNull(role);

        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        if (normalizedKeyword != null) {
            wrapper.and(query -> query.like(User::getUsername, normalizedKeyword)
                    .or()
                    .like(User::getNickname, normalizedKeyword)
                    .or()
                    .like(User::getEmail, normalizedKeyword));
        }
        if (normalizedRole != null) {
            if (!ALLOWED_PLATFORM_ROLES.contains(normalizedRole)) {
                throw new BusinessException(StatusCode.BAD_REQUEST, "无效的用户角色");
            }
            wrapper.eq(User::getRole, normalizedRole);
        }
        wrapper.orderByDesc(User::getCreatedAt);

        Page<User> result = userMapper.selectPage(new Page<>(safePage, safePageSize), wrapper);
        List<UserInfoDTO> records =
                result.getRecords().stream().map(this::convertToUserInfoDTO).toList();
        return PageResult.of(result.getCurrent(), result.getSize(), result.getTotal(), records);
    }

    @Override
    public List<UserSearchDTO> searchUsers(String keyword) {
        String normalizedKeyword = trimToNull(keyword);
        if (normalizedKeyword == null) {
            return List.of();
        }
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.and(query -> query.like(User::getUsername, normalizedKeyword)
                        .or()
                        .like(User::getNickname, normalizedKeyword))
                .orderByDesc(User::getCreatedAt)
                .last("LIMIT 10");
        return userMapper.selectList(wrapper).stream()
                .map(user -> UserSearchDTO.builder()
                        .id(user.getId())
                        .username(user.getUsername())
                        .nickname(user.getNickname())
                        .build())
                .toList();
    }

    @Override
    @Transactional
    public UserInfoDTO updateUserRole(Long userId, String role) {
        String normalizedRole = trimToNull(role);
        if (normalizedRole == null || !ASSIGNABLE_PLATFORM_ROLES.contains(normalizedRole)) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "可分配身份只能是待分配、普通用户或 AI 配置员");
        }

        Long currentUserId = JwtUtils.getCurrentUserId();
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "用户不存在");
        }
        if (CommonConstants.ROLE_ADMIN.equals(user.getRole()) || Boolean.TRUE.equals(user.getPlatformAdmin())) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "唯一超级管理员账号不能被修改");
        }

        user.setRole(normalizedRole);
        user.setPlatformAdmin(false);
        userMapper.updateById(user);
        log.info("USER_ROLE_UPDATED operatorId={} userId={} role={}", currentUserId, userId, normalizedRole);
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
            ServletRequestAttributes attrs = (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();
            return IpUtils.getClientIp(attrs.getRequest(), trustedProxyHeaders);
        } catch (IllegalStateException e) {
            return "unknown";
        }
    }

    /**
     * 更新用户主题偏好
     *
     * @param themePreference 主题偏好（light/dark/system）
     * @return 用户信息
     */
    @Override
    public UserInfoDTO updateThemePreference(String themePreference) {
        Long userId = jwtUtils.getCurrentUserId();
        User user = userMapper.selectById(userId);
        if (user == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "用户不存在");
        }
        User update = new User();
        update.setId(userId);
        update.setThemePreference(themePreference);
        userMapper.updateById(update);
        user.setThemePreference(themePreference);
        return convertToUserInfoDTO(user);
    }

    @Override
    @Transactional
    public String updateAvatar(Long userId, MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new BusinessException("请选择头像图片");
        }
        if (file.getSize() > AVATAR_MAX_SIZE) {
            throw new BusinessException("头像图片不能超过 2MB");
        }
        String ext = detectImageExtension(file);
        try {
            User user = userMapper.selectById(userId);
            if (user == null) {
                throw new BusinessException("用户不存在");
            }
            Path dir = resolveAvatarDir();
            Files.createDirectories(dir);
            // 移除旧头像（扩展名可能变化），写入新文件
            removeAvatarFiles(dir, userId);
            Path target = dir.resolve(userId + "." + ext);
            file.transferTo(target.toAbsolutePath());
            user.setAvatar(AVATAR_DB_PREFIX + userId + "." + ext);
            userMapper.updateById(user);
            log.info("用户 {} 头像已更新: {}", userId, target.getFileName());
            return "/api/user/avatar/" + userId;
        } catch (IOException e) {
            log.error("头像保存失败: userId={}", userId, e);
            throw new BusinessException("头像保存失败，请稍后重试");
        }
    }

    @Override
    public Optional<Path> getAvatarFile(Long userId) {
        Path dir = resolveAvatarDir();
        return AVATAR_TYPES.keySet().stream()
                .map(ext -> dir.resolve(userId + "." + ext))
                .filter(Files::exists)
                .findFirst();
    }

    /** 头像目录解析：相对路径相对应用工作目录；绝对路径直接使用（测试注入 @TempDir） */
    private Path resolveAvatarDir() {
        Path configured = Paths.get(avatarDir);
        return configured.isAbsolute() ? configured : Paths.get(System.getProperty("user.dir"), avatarDir);
    }

    /** 按魔数识别真实图片类型；不匹配时拒绝（防伪装扩展名） */
    private String detectImageExtension(MultipartFile file) {
        String name = file.getOriginalFilename() == null ? "" : file.getOriginalFilename().toLowerCase(Locale.ROOT);
        String ext = name.contains(".")
                ? name.substring(name.lastIndexOf('.') + 1)
                : "";
        if (!AVATAR_TYPES.containsKey(ext)) {
            throw new BusinessException("仅支持 JPG / PNG / WEBP / GIF 格式图片");
        }
        byte[] magic = new byte[12];
        int read;
        try {
            read = file.getInputStream().readNBytes(magic, 0, magic.length);
        } catch (IOException e) {
            throw new BusinessException("头像读取失败，请重试");
        }
        boolean isJpeg = read >= 3 && (magic[0] & 0xFF) == 0xFF && (magic[1] & 0xFF) == 0xD8 && (magic[2] & 0xFF) == 0xFF;
        boolean isPng = read >= 4 && (magic[0] & 0xFF) == 0x89 && magic[1] == 0x50 && magic[2] == 0x4E && magic[3] == 0x47;
        boolean isGif = read >= 4 && magic[0] == 0x47 && magic[1] == 0x49 && magic[2] == 0x46 && magic[3] == 0x38;
        boolean isWebP = read >= 12 && magic[0] == 0x52 && magic[1] == 0x49 && magic[2] == 0x46 && magic[3] == 0x46
                && magic[8] == 0x57 && magic[9] == 0x45 && magic[10] == 0x42 && magic[11] == 0x50;
        boolean matches = switch (ext) {
            case "jpg", "jpeg" -> isJpeg;
            case "png" -> isPng;
            case "gif" -> isGif;
            case "webp" -> isWebP;
            default -> false;
        };
        if (!matches) {
            throw new BusinessException("图片内容与扩展名不符，请选择真实的图片文件");
        }
        return ext;
    }

    private void removeAvatarFiles(Path avatarDir, Long userId) {
        for (String ext : AVATAR_TYPES.keySet()) {
            try {
                Files.deleteIfExists(avatarDir.resolve(userId + "." + ext));
            } catch (IOException e) {
                log.warn("删除旧头像失败: userId={} ext={}", userId, ext, e);
            }
        }
    }

    /** DB 存相对路径，DTO 统一转换为可访问 URL；未设置头像时返回 null（前端回退首字母头像） */
    private String avatarUrl(User user) {
        return user.getAvatar() == null || user.getAvatar().isBlank()
                ? null
                : "/api/user/avatar/" + user.getId();
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
                .themePreference(user.getThemePreference())
                .avatar(avatarUrl(user))
                .role(user.getRole())
                .status(user.getStatus())
                .lastLoginTime(user.getLastLoginTime())
                .createdAt(user.getCreatedAt())
                .build();
    }
}
