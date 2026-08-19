package com.hfusionhub.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.result.R;
import com.hfusionhub.service.OidcService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * SSO/OIDC 登录入口。
 *
 * <p>仅服务外部 IdP 的授权码流程：{@code /user/sso/authorize} 302 跳转 IdP，
 * {@code /user/sso/callback} 消费授权码并回跳前端携带 satoken。路由位于
 * {@code /user/sso/**}，已在 {@link com.hfusionhub.config.SaTokenConfig}
 * 的登录校验白名单中放行（IdP 回跳时用户天然未登录）。
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/user/sso")
@RequiredArgsConstructor
@Tag(name = "SSO 登录", description = "外部 OIDC 身份提供商单点登录")
public class SsoController {

    private final OidcService oidcService;
    private final ObjectMapper objectMapper;

    /**
     * 提供方信息 — 前端据此决定是否展示「SSO 登录」按钮。
     *
     * @return enabled + providerName
     */
    @GetMapping("/providers")
    @Operation(summary = "SSO 提供方信息", description = "返回是否启用及提供方名称")
    public R<Map<String, Object>> providers() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("enabled", oidcService.isEnabled());
        data.put("providerName", oidcService.getProviderName());
        return R.ok(data);
    }

    /**
     * 发起 SSO 登录：302 重定向到 IdP 授权端点。
     *
     * @param response HTTP 响应
     * @throws IOException 重定向失败
     */
    @GetMapping("/authorize")
    @Operation(summary = "发起 SSO 登录", description = "302 跳转到 IdP 授权端点")
    public void authorize(HttpServletResponse response) throws IOException {
        response.sendRedirect(oidcService.buildAuthorizationUrl());
    }

    /**
     * IdP 授权码回调：换 token → 建号/关联 → Sa-Token 登录 → 携带 satoken 回前端。
     *
     * @param code     授权码
     * @param state    一次性防 CSRF state
     * @param response HTTP 响应
     * @throws IOException 重定向失败
     */
    @GetMapping("/callback")
    @Operation(summary = "SSO 回调", description = "IdP 授权码回调：换 token、建号/关联、登录并回跳前端携带 satoken")
    public void callback(
            @RequestParam String code,
            @RequestParam(required = false) String state,
            HttpServletResponse response) throws IOException {
        String token = oidcService.loginWithCode(code, state);
        String target = oidcService.getFrontendRedirectUri();
        if (target == null || target.isBlank()) {
            // 未配置前端回跳地址时直接返回 JSON（供非浏览器 / 测试使用）
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write(objectMapper.writeValueAsString(R.ok("登录成功", token)));
            return;
        }
        // 会话令牌放 URL fragment（#token=...）而非 query：fragment 不会进入
        // 浏览器历史、代理/访问日志与 Referer 头。前端 SsoCallback 页负责解析。
        response.sendRedirect(target + "#token=" + URLEncoder.encode(token, StandardCharsets.UTF_8));
    }
}
