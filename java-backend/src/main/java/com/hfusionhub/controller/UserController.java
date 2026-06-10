package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.AdminPasswordResetDTO;
import com.hfusionhub.dto.PasswordChangeDTO;
import com.hfusionhub.dto.ThemePreferenceUpdateDTO;
import com.hfusionhub.dto.UserInfoDTO;
import com.hfusionhub.dto.UserLoginDTO;
import com.hfusionhub.dto.UserRegisterDTO;
import com.hfusionhub.dto.UserRoleUpdateDTO;
import com.hfusionhub.dto.UserSearchDTO;
import com.hfusionhub.dto.UserUpdateDTO;
import com.hfusionhub.service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 用户控制器
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/user")
@RequiredArgsConstructor
@Tag(name = "用户管理", description = "用户登录、注册、信息管理")
public class UserController {

    private final UserService userService;

    /**
     * 用户登录
     *
     * @param loginDTO 登录请求
     * @return Token
     */
    @PostMapping("/login")
    @Operation(summary = "用户登录", description = "用户名密码登录，返回Token")
    public R<String> login(@Valid @RequestBody UserLoginDTO loginDTO) {
        String token = userService.login(loginDTO);
        return R.ok("登录成功", token);
    }

    /**
     * 用户注册
     *
     * @param registerDTO 注册请求
     * @return 用户信息
     */
    @PostMapping("/register")
    @Operation(summary = "用户注册", description = "用户名密码注册")
    public R<UserInfoDTO> register(@Valid @RequestBody UserRegisterDTO registerDTO) {
        UserInfoDTO userInfo = userService.register(registerDTO);
        return R.ok("注册成功", userInfo);
    }

    /**
     * 用户登出
     *
     * @return 结果
     */
    @PostMapping("/logout")
    @Operation(summary = "用户登出", description = "退出登录")
    public R<Void> logout() {
        userService.logout();
        return R.ok();
    }

    /**
     * 获取当前用户信息
     *
     * @return 用户信息
     */
    @GetMapping("/info")
    @Operation(summary = "获取当前用户信息", description = "获取当前登录用户的信息")
    public R<UserInfoDTO> getCurrentUser() {
        UserInfoDTO userInfo = userService.getCurrentUser();
        return R.ok(userInfo);
    }

    /**
     * 更新用户信息
     *
     * @param updateDTO 更新请求
     * @return 用户信息
     */
    @PutMapping("/info")
    @Operation(summary = "更新用户信息", description = "更新当前用户的信息")
    public R<UserInfoDTO> updateUser(@Valid @RequestBody UserUpdateDTO updateDTO) {
        UserInfoDTO userInfo = userService.updateUser(updateDTO);
        return R.ok("更新成功", userInfo);
    }

    /**
     * 根据用户ID获取用户信息（管理员接口）
     *
     * @param userId 用户ID
     * @return 用户信息
     */
    @SaCheckRole("admin")
    @GetMapping("/{userId}")
    @Operation(summary = "根据ID获取用户信息", description = "根据用户ID获取用户信息（管理员接口）")
    public R<UserInfoDTO> getUserById(@PathVariable Long userId) {
        UserInfoDTO userInfo = userService.getUserById(userId);
        return R.ok(userInfo);
    }

    @SaCheckRole("admin")
    @GetMapping("/list")
    @Operation(summary = "分页查询用户", description = "管理员查看用户并分配平台身份")
    public R<PageResult<UserInfoDTO>> listUsers(
            @RequestParam(defaultValue = "1") long page,
            @RequestParam(defaultValue = "20") long pageSize,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String role) {
        return R.ok(userService.listUsers(page, pageSize, keyword, role));
    }

    @GetMapping("/search")
    @Operation(summary = "搜索用户", description = "按用户名/昵称模糊搜索用户（登录用户可用，用于共享知识库等场景；仅返回 id、用户名、昵称）")
    public R<List<UserSearchDTO>> searchUsers(@RequestParam String keyword) {
        return R.ok(userService.searchUsers(keyword));
    }

    @PostMapping("/password")
    @Operation(summary = "修改密码", description = "校验当前密码后更新为新密码")
    public R<Void> changePassword(@Valid @RequestBody PasswordChangeDTO dto) {
        userService.changePassword(dto);
        return R.ok("密码已更新", null);
    }

    @SaCheckRole("admin")
    @PutMapping("/{userId}/password")
    @Operation(summary = "重置用户密码", description = "管理员为忘记密码的用户设置临时新密码（无需旧密码；不可用于自己，自己走「修改密码」）")
    public R<UserInfoDTO> resetUserPassword(@PathVariable Long userId,
                                            @Valid @RequestBody AdminPasswordResetDTO dto) {
        return R.ok("密码已重置，请将临时密码通过线下渠道告知用户", userService.resetUserPassword(userId, dto));
    }

    @SaCheckRole("admin")
    @PutMapping("/{userId}/role")
    @Operation(summary = "修改用户身份", description = "管理员分配普通用户、AI 配置员或系统管理员身份")
    public R<UserInfoDTO> updateUserRole(@PathVariable Long userId, @Valid @RequestBody UserRoleUpdateDTO dto) {
        return R.ok("身份已更新", userService.updateUserRole(userId, dto.getRole()));
    }

    /**
     * 更新主题偏好
     *
     * @param request 主题偏好请求
     * @return 用户信息
     */
    @PatchMapping("/theme-preference")
    @Operation(summary = "更新主题偏好", description = "更新当前用户的主题偏好（light/dark/system）")
    public R<UserInfoDTO> updateThemePreference(@Valid @RequestBody ThemePreferenceUpdateDTO request) {
        UserInfoDTO userInfo = userService.updateThemePreference(request.getThemePreference());
        return R.ok("主题偏好已更新", userInfo);
    }
}
