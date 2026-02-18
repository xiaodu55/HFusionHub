package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.UserInfoDTO;
import com.hfusionhub.dto.UserLoginDTO;
import com.hfusionhub.dto.UserRegisterDTO;
import com.hfusionhub.dto.UserUpdateDTO;
import com.hfusionhub.service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
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
}
