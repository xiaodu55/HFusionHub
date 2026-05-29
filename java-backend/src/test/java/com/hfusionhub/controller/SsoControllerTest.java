package com.hfusionhub.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.result.R;
import com.hfusionhub.service.OidcService;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockHttpServletResponse;

/**
 * 纯单元测试：SsoController（SSO 登录入口）。
 */
@ExtendWith(MockitoExtension.class)
class SsoControllerTest {

    @Mock private OidcService oidcService;

    private final ObjectMapper objectMapper = new ObjectMapper();
    private SsoController controller;

    private SsoController newController() {
        return new SsoController(oidcService, objectMapper);
    }

    @Test
    void providers_disabled_reportsEnabledFalse() {
        controller = newController();
        when(oidcService.isEnabled()).thenReturn(false);
        when(oidcService.getProviderName()).thenReturn("generic");
        R<Map<String, Object>> result = controller.providers();
        assertEquals(200, result.getCode());
        assertEquals(Boolean.FALSE, result.getData().get("enabled"));
        assertEquals("generic", result.getData().get("providerName"));
    }

    @Test
    void providers_enabled_reportsProviderName() {
        controller = newController();
        when(oidcService.isEnabled()).thenReturn(true);
        when(oidcService.getProviderName()).thenReturn("wecom");
        R<Map<String, Object>> result = controller.providers();
        assertEquals(200, result.getCode());
        assertEquals(Boolean.TRUE, result.getData().get("enabled"));
        assertEquals("wecom", result.getData().get("providerName"));
    }

    @Test
    void authorize_redirectsToIdp() throws Exception {
        controller = newController();
        when(oidcService.buildAuthorizationUrl()).thenReturn("https://idp.example.com/authorize?state=abc");
        MockHttpServletResponse response = new MockHttpServletResponse();
        controller.authorize(response);
        assertEquals(302, response.getStatus());
        assertTrue(response.getRedirectedUrl().startsWith("https://idp.example.com/authorize?state=abc"));
    }

    @Test
    void callback_withoutFrontendRedirect_returnsTokenJson() throws Exception {
        controller = newController();
        when(oidcService.loginWithCode("code-1", "state-1")).thenReturn("sso-token");
        when(oidcService.getFrontendRedirectUri()).thenReturn("");
        HttpServletResponse response = new MockHttpServletResponse();
        controller.callback("code-1", "state-1", response);
        assertTrue(response.getStatus() < 400);
    }
}
