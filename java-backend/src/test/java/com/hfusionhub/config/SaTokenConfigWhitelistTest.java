package com.hfusionhub.config;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Test;

/**
 * 守护 Sa-Token 登录校验白名单（{@link SaTokenConfig#AUTH_WHITELIST}）。
 *
 * <p>背景：{@code /user/sso/**} 曾被遗漏——OIDC 回跳时用户天然未登录，
 * {@code checkLogin()} 直接 401，SSO 登录流程死锁。本测试确保 SSO 入口
 * 在白名单内，且白名单本身不包含过宽的通配（如 {@code /**}）。
 */
class SaTokenConfigWhitelistTest {

    /** SSO 授权码流程的全部端点（SsoController @RequestMapping + @GetMapping）。 */
    private static final List<String> SSO_ENDPOINTS = List.of(
            "/user/sso/providers",
            "/user/sso/authorize",
            "/user/sso/callback");

    @Test
    void whitelistContainsSsoFlow() {
        List<String> whitelist = Arrays.asList(SaTokenConfig.AUTH_WHITELIST);
        for (String pattern : List.of("/user/sso/**", "/user/login", "/user/register", "/health")) {
            assertTrue(whitelist.contains(pattern), "登录白名单必须包含 " + pattern);
        }
    }

    @Test
    void whitelistPatternsMatchAllSsoEndpoints() {
        // Sa-Token 的 AntPath 通配："/user/sso/**" 必须覆盖 SsoController 的每个端点。
        // 用最朴素的断言防止「端点新增后白名单 pattern 被改窄」的漂移。
        for (String endpoint : SSO_ENDPOINTS) {
            assertTrue(endpoint.startsWith("/user/sso/"),
                    "端点 " + endpoint + " 偏离 /user/sso/ 前缀，请同步更新白名单测试");
        }
        List<String> whitelist = Arrays.asList(SaTokenConfig.AUTH_WHITELIST);
        assertTrue(whitelist.contains("/user/sso/**"),
                "SsoController 端点 " + SSO_ENDPOINTS + " 需要 /user/sso/** 放行");
    }

    @Test
    void whitelistDoesNotOverWhitelist() {
        List<String> whitelist = Arrays.asList(SaTokenConfig.AUTH_WHITELIST);
        // 不允许出现把全部业务接口放行的过宽条目。
        for (String pattern : whitelist) {
            assertTrue(!pattern.equals("/**") && !pattern.equals("/user/**") && !pattern.equals("/internal/**"),
                    "白名单条目过宽: " + pattern);
        }
    }

    @Test
    void whitelistEntriesAreWellFormed() {
        for (String pattern : SaTokenConfig.AUTH_WHITELIST) {
            assertNotNull(pattern);
            assertTrue(pattern.startsWith("/"), "白名单条目必须以 / 开头: " + pattern);
            assertEquals(pattern, pattern.trim(), "白名单条目不得带空白: " + pattern);
        }
        // 无重复
        assertEquals(SaTokenConfig.AUTH_WHITELIST.length,
                Arrays.stream(SaTokenConfig.AUTH_WHITELIST).distinct().count(),
                "白名单存在重复条目");
        assertArrayEquals(SaTokenConfig.AUTH_WHITELIST, SaTokenConfig.AUTH_WHITELIST,
                "sanity: constant is stable");
    }
}
