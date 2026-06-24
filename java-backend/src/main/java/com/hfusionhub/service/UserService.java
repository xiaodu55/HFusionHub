package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.AdminPasswordResetDTO;
import com.hfusionhub.dto.PasswordChangeDTO;
import com.hfusionhub.dto.UserInfoDTO;
import com.hfusionhub.dto.UserLoginDTO;
import com.hfusionhub.dto.UserRegisterDTO;
import com.hfusionhub.dto.UserSearchDTO;
import com.hfusionhub.dto.UserUpdateDTO;
import java.util.List;

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

    PageResult<UserInfoDTO> listUsers(long page, long pageSize, String keyword, String role);

    /**
     * 轻量搜索用户（按用户名/昵称模糊匹配，供共享知识库等场景使用）
     *
     * @param keyword 搜索关键字
     * @return 轻量用户信息列表（不含敏感字段）
     */
    List<UserSearchDTO> searchUsers(String keyword);

    /**
     * 修改当前用户密码（校验旧密码后更新）
     *
     * @param dto 旧密码 + 新密码
     */
    void changePassword(PasswordChangeDTO dto);

    /**
     * 管理员重置用户密码（无需旧密码；用于忘记密码场景）
     *
     * @param userId 目标用户 ID
     * @param dto 临时新密码
     * @return 更新后的用户信息
     */
    UserInfoDTO resetUserPassword(Long userId, AdminPasswordResetDTO dto);

    UserInfoDTO updateUserRole(Long userId, String role);

    /**
     * 更新用户主题偏好
     *
     * @param themePreference 主题偏好（light/dark/system）
     * @return 用户信息
     */
    UserInfoDTO updateThemePreference(String themePreference);

    /**
     * 上传当前用户头像（校验图片类型/大小后落盘 uploads/avatars 并更新 avatar 字段）
     *
     * @param userId 用户 ID
     * @param file 头像图片文件（jpeg/png/webp/gif，≤2MB）
     * @return 头像访问 URL（/api/user/avatar/{userId}）
     */
    String updateAvatar(Long userId, org.springframework.web.multipart.MultipartFile file);

    /**
     * 读取用户头像文件（不存在时返回 empty）
     *
     * @param userId 用户 ID
     * @return 头像文件路径
     */
    java.util.Optional<java.nio.file.Path> getAvatarFile(Long userId);
}
