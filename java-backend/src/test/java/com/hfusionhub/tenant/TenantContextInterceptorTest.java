package com.hfusionhub.tenant;

import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.Tenant;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.TenantMapper;
import com.hfusionhub.mapper.TenantMemberMapper;
import com.hfusionhub.mapper.UserMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.when;

/**
 * Unit tests for {@link TenantContextInterceptor} — strict fail-closed tenant
 * resolution, the guarded callback path, and X-Target-Tenant validation.
 */
class TenantContextInterceptorTest {

    private UserMapper userMapper;
    private TenantMemberMapper tenantMemberMapper;
    private TenantMapper tenantMapper;
    private TenantContextInterceptor interceptor;
    private MockHttpServletRequest request;
    private MockHttpServletResponse response;

    @BeforeEach
    void setUp() {
        userMapper = mock(UserMapper.class);
        tenantMemberMapper = mock(TenantMemberMapper.class);
        tenantMapper = mock(TenantMapper.class);
        interceptor = new TenantContextInterceptor(userMapper, tenantMemberMapper, tenantMapper);
        ReflectionTestUtils.setField(interceptor, "strict", true);
        ReflectionTestUtils.setField(interceptor, "defaultTenantId", 1L);
        request = new MockHttpServletRequest();
        request.setMethod("GET");
        request.setRequestURI("/api/knowledge-base/list");
        request.setServletPath("/knowledge-base/list");
        response = new MockHttpServletResponse();
    }

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    // ── Fail-closed: unauthenticated, no context → 403 ──────────────────

    @Test
    void unauthenticatedNonCallbackRejectedInStrictMode() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(false);
            assertFalse(interceptor.preHandle(request, response, null));
            assertEquals(403, response.getStatus());
            assertNull(TenantContext.getTenantId());
        }
    }

    @Test
    void nonStrictModeDefaultsToTenant1() {
        ReflectionTestUtils.setField(interceptor, "strict", false);
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(false);
            assertTrue(interceptor.preHandle(request, response, null));
            assertEquals(1L, TenantContext.getTenantId());
        }
    }

    // ── Guarded callback: X-Tenant-Id honoured ONLY when verified ───────

    @Test
    void unsignedCallbackCannotSetTenant() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(false);
            request.setServletPath("/vectorize/42/callback");
            request.addHeader("X-Tenant-Id", "5");

            assertFalse(interceptor.preHandle(request, response, null));
            assertEquals(403, response.getStatus());
            assertNull(TenantContext.getTenantId());
        }
    }

    @Test
    void verifiedCallbackHonoursXTenantId() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(false);
            request.setServletPath("/vectorize/42/callback");
            request.setAttribute(TenantContextInterceptor.CALLBACK_VERIFIED_ATTR, Boolean.TRUE);
            request.addHeader("X-Tenant-Id", "5");

            assertTrue(interceptor.preHandle(request, response, null));
            assertEquals(5L, TenantContext.getTenantId());
        }
    }

    @Test
    void callbackPathOutsideVectorizeRejected() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(false);
            request.setServletPath("/other/42/callback");
            request.setAttribute(TenantContextInterceptor.CALLBACK_VERIFIED_ATTR, Boolean.TRUE);
            request.addHeader("X-Tenant-Id", "5");

            assertFalse(interceptor.preHandle(request, response, null));
            assertEquals(403, response.getStatus());
            assertNull(TenantContext.getTenantId());
        }
    }

    // ── Authenticated: tenant from login + membership, X-Tenant-Id ignored ─

    @Test
    void authenticatedUserUsesOwnTenantAndIgnoresXTenantId() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(true);
            jwt.when(JwtUtils::getCurrentUserId).thenReturn(1L);
            User user = new User();
            user.setId(1L);
            user.setTenantId(7L);
            when(userMapper.selectById(1L)).thenReturn(user);
            when(tenantMemberMapper.selectByTenantAndUser(7L, 1L)).thenReturn(new TenantMember());
            request.addHeader("X-Tenant-Id", "999");

            assertTrue(interceptor.preHandle(request, response, null));
            assertEquals(7L, TenantContext.getTenantId());
            assertFalse(TenantContext.isCrossTenant());
        }
    }

    @Test
    void authenticatedUserWithoutMembershipRejected() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(true);
            jwt.when(JwtUtils::getCurrentUserId).thenReturn(1L);
            User user = new User();
            user.setId(1L);
            user.setTenantId(7L);
            when(userMapper.selectById(1L)).thenReturn(user);
            when(tenantMemberMapper.selectByTenantAndUser(7L, 1L)).thenReturn(null);

            assertFalse(interceptor.preHandle(request, response, null));
            assertEquals(403, response.getStatus());
            assertNull(TenantContext.getTenantId());
        }
    }

    // ── X-Target-Tenant: no silent fallback ─────────────────────────────

    private User platformAdmin() {
        User admin = new User();
        admin.setId(1L);
        admin.setTenantId(1L);
        admin.setPlatformAdmin(true);
        return admin;
    }

    @Test
    void invalidXTargetTenantReturns403() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(true);
            jwt.when(JwtUtils::getCurrentUserId).thenReturn(1L);
            when(userMapper.selectById(1L)).thenReturn(platformAdmin());
            request.addHeader("X-Target-Tenant", "abc");

            assertFalse(interceptor.preHandle(request, response, null));
            assertEquals(403, response.getStatus());
            assertNull(TenantContext.getTenantId());
        }
    }

    @Test
    void nonNumericZeroXTargetTenantReturns403() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(true);
            jwt.when(JwtUtils::getCurrentUserId).thenReturn(1L);
            when(userMapper.selectById(1L)).thenReturn(platformAdmin());
            request.addHeader("X-Target-Tenant", "0");

            assertFalse(interceptor.preHandle(request, response, null));
            assertEquals(403, response.getStatus());
        }
    }

    @Test
    void nonexistentXTargetTenantReturns404() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(true);
            jwt.when(JwtUtils::getCurrentUserId).thenReturn(1L);
            when(userMapper.selectById(1L)).thenReturn(platformAdmin());
            request.addHeader("X-Target-Tenant", "999");
            when(tenantMapper.selectById(999L)).thenReturn(null);

            assertFalse(interceptor.preHandle(request, response, null));
            assertEquals(404, response.getStatus());
            assertNull(TenantContext.getTenantId());
        }
    }

    @Test
    void inactiveXTargetTenantReturns404() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(true);
            jwt.when(JwtUtils::getCurrentUserId).thenReturn(1L);
            when(userMapper.selectById(1L)).thenReturn(platformAdmin());
            request.addHeader("X-Target-Tenant", "999");
            Tenant inactive = new Tenant();
            inactive.setId(999L);
            inactive.setStatus("disabled");
            when(tenantMapper.selectById(999L)).thenReturn(inactive);

            assertFalse(interceptor.preHandle(request, response, null));
            assertEquals(404, response.getStatus());
        }
    }

    @Test
    void activeXTargetTenantSwitchesContextAndSetsCrossTenant() {
        try (MockedStatic<JwtUtils> jwt = mockStatic(JwtUtils.class)) {
            jwt.when(JwtUtils::isLogin).thenReturn(true);
            jwt.when(JwtUtils::getCurrentUserId).thenReturn(1L);
            when(userMapper.selectById(1L)).thenReturn(platformAdmin());
            request.addHeader("X-Target-Tenant", "999");
            Tenant active = new Tenant();
            active.setId(999L);
            active.setStatus("active");
            when(tenantMapper.selectById(999L)).thenReturn(active);

            assertTrue(interceptor.preHandle(request, response, null));
            assertEquals(999L, TenantContext.getTenantId());
            assertTrue(TenantContext.isCrossTenant());
        }
    }
}
