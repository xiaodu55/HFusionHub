package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.TenantMemberMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.OidcService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

/**
 * 纯单元测试：OidcService 通用 OIDC 客户端（授权码流程）。
 * 通过 ReflectionTestUtils 注入 app.oidc.* @Value 字段，Mockito 模拟
 * RestTemplate / RedisTemplate / Mapper。
 */
@ExtendWith(MockitoExtension.class)
class OidcServiceTest {

    private static final String TOKEN_ENDPOINT = "https://idp.example.com/token";
    private static final String USERINFO_ENDPOINT = "https://idp.example.com/userinfo";

    @Mock private RestTemplate restTemplate;
    @Mock private RedisTemplate<String, Object> redisTemplate;
    @Mock private ValueOperations<String, Object> valueOperations;
    @Mock private UserMapper userMapper;
    @Mock private TenantMemberMapper tenantMemberMapper;

    private final ObjectMapper objectMapper = new ObjectMapper();
    private OidcService service;

    @BeforeEach
    void setUp() {
        service = new OidcService(restTemplate, redisTemplate, userMapper, tenantMemberMapper, objectMapper);
        // app.oidc.* 配置（默认关闭 → 各用例按需开启）
        ReflectionTestUtils.setField(service, "enabled", true);
        ReflectionTestUtils.setField(service, "providerName", "generic");
        ReflectionTestUtils.setField(service, "authorizationEndpoint", "https://idp.example.com/authorize");
        ReflectionTestUtils.setField(service, "tokenEndpoint", TOKEN_ENDPOINT);
        ReflectionTestUtils.setField(service, "userInfoEndpoint", USERINFO_ENDPOINT);
        ReflectionTestUtils.setField(service, "clientId", "client-1");
        ReflectionTestUtils.setField(service, "clientSecret", "secret-1");
        ReflectionTestUtils.setField(service, "redirectUri", "https://app.example.com/api/user/sso/callback");
        ReflectionTestUtils.setField(service, "frontendRedirectUri", "https://app.example.com/#/sso/callback");
        ReflectionTestUtils.setField(service, "autoProvision", true);
        // 未用到的用例（如 disabled 配置）不应因多余 stub 失败 → lenient
        org.mockito.Mockito.lenient().when(redisTemplate.opsForValue()).thenReturn(valueOperations);
    }

    private void stubStatePresent() {
        when(valueOperations.get(anyString())).thenReturn(Boolean.TRUE);
    }

    private void stubTokenExchange() throws Exception {
        JsonNode tokenResponse =
                objectMapper.readTree("{\"access_token\":\"at-123\",\"token_type\":\"Bearer\"}");
        when(restTemplate.postForObject(eq(TOKEN_ENDPOINT), any(), eq(JsonNode.class)))
                .thenReturn(tokenResponse);
    }

    private void stubUserInfo(String sub, String email, String preferredUsername, String name) throws Exception {
        JsonNode info = objectMapper.readTree(
                "{\"sub\":\"" + sub + "\",\"preferred_username\":\"" + preferredUsername
                        + "\",\"email\":\"" + email + "\",\"name\":\"" + name + "\"}");
        when(restTemplate.exchange(eq(USERINFO_ENDPOINT), eq(HttpMethod.GET), any(), eq(JsonNode.class)))
                .thenReturn(ResponseEntity.ok(info));
    }

    @Test
    void buildAuthorizationUrl_whenDisabled_throws() {
        ReflectionTestUtils.setField(service, "enabled", false);
        BusinessException ex =
                assertThrows(BusinessException.class, () -> service.buildAuthorizationUrl());
        assertEquals(StatusCode.BAD_REQUEST, ex.getCode());
    }

    @Test
    void buildAuthorizationUrl_whenConfigured_containsExpectedParams() {
        String url = service.buildAuthorizationUrl();
        assertTrue(url.startsWith("https://idp.example.com/authorize?"));
        assertTrue(url.contains("response_type=code"));
        assertTrue(url.contains("client_id=client-1"));
        assertTrue(url.contains("redirect_uri="));
        assertTrue(url.contains("scope="));
        assertTrue(url.contains("state="));
        // state 落盘（防 CSRF）
        verify(valueOperations).set(anyString(), eq(Boolean.TRUE), any());
    }

    @Test
    void loginWithCode_whenStateAbsent_throwsAndConsumes() throws Exception {
        // state 不存在 → 拒绝
        BusinessException ex =
                assertThrows(BusinessException.class, () -> service.loginWithCode("code-1", "stale-state"));
        assertEquals(StatusCode.BAD_REQUEST, ex.getCode());
        verify(valueOperations).get("oidc:state:stale-state");
        verify(redisTemplate).delete("oidc:state:stale-state");
        verify(userMapper, never()).insert(any(User.class));
    }

    @Test
    void loginWithCode_newUser_provisionsAndLogsIn() throws Exception {
        stubStatePresent();
        stubTokenExchange();
        stubUserInfo("sub-42", "alice@corp.com", "alice", "Alice");
        // 无既有账号：selectOne(subject) → null，selectOne(email) → null
        when(userMapper.selectOne(any())).thenReturn(null);
        // MyBatis Plus insert 回填主键
        when(userMapper.insert(any(User.class)))
                .thenAnswer(inv -> {
                    ((User) inv.getArgument(0)).setId(99L);
                    return 1;
                });

        try (MockedStatic<JwtUtils> mocked = mockStatic(JwtUtils.class)) {
            mocked.when(JwtUtils::getTokenValue).thenReturn("sso-token-1");
            String token = service.loginWithCode("code-1", "state-1");

            assertEquals("sso-token-1", token);
            verify(userMapper).insert(any(User.class));
            verify(tenantMemberMapper).insert(any());
            mocked.verify(() -> JwtUtils.login(99L));
        }
    }

    @Test
    void loginWithCode_existingSubject_logsInWithoutProvision() throws Exception {
        stubStatePresent();
        stubTokenExchange();
        stubUserInfo("sub-7", "bob@corp.com", "bob", "Bob");
        User existing = new User();
        existing.setId(7L);
        existing.setUsername("bob");
        existing.setStatus(0);
        when(userMapper.selectOne(any())).thenReturn(existing);

        try (MockedStatic<JwtUtils> mocked = mockStatic(JwtUtils.class)) {
            mocked.when(JwtUtils::getTokenValue).thenReturn("sso-token-2");
            String token = service.loginWithCode("code-2", "state-2");

            assertEquals("sso-token-2", token);
            verify(userMapper, never()).insert(any(User.class));
            verify(userMapper).updateById(existing);
            mocked.verify(() -> JwtUtils.login(7L));
        }
    }

    @Test
    void loginWithCode_disabledUser_throws() throws Exception {
        stubStatePresent();
        stubTokenExchange();
        stubUserInfo("sub-9", "charlie@corp.com", "charlie", "Charlie");
        User disabled = new User();
        disabled.setId(9L);
        disabled.setStatus(1);
        when(userMapper.selectOne(any())).thenReturn(disabled);

        BusinessException ex =
                assertThrows(BusinessException.class, () -> service.loginWithCode("code-3", "state-3"));
        assertEquals(StatusCode.USER_DISABLED, ex.getCode());
    }

    @Test
    void loginWithCode_tokenExchangeFailure_throws() throws Exception {
        stubStatePresent();
        when(restTemplate.postForObject(eq(TOKEN_ENDPOINT), any(), eq(JsonNode.class)))
                .thenReturn(objectMapper.readTree("{\"error\":\"invalid_grant\"}"));

        BusinessException ex =
                assertThrows(BusinessException.class, () -> service.loginWithCode("code-4", "state-4"));
        assertEquals(StatusCode.LOGIN_ERROR, ex.getCode());
        verify(userMapper, never()).insert(any(User.class));
    }

    @Test
    void loginWithCode_userInfoMissingSub_throws() throws Exception {
        stubStatePresent();
        stubTokenExchange();
        when(restTemplate.exchange(eq(USERINFO_ENDPOINT), eq(HttpMethod.GET), any(), eq(JsonNode.class)))
                .thenReturn(ResponseEntity.ok(objectMapper.readTree("{\"email\":\"no-sub@corp.com\"}")));

        BusinessException ex =
                assertThrows(BusinessException.class, () -> service.loginWithCode("code-5", "state-5"));
        assertEquals(StatusCode.LOGIN_ERROR, ex.getCode());
        verify(userMapper, never()).insert(any(User.class));
    }

    @Test
    void loginWithCode_provisionUser_getsRandomPassword() throws Exception {
        stubStatePresent();
        stubTokenExchange();
        stubUserInfo("sub-11", "dave@corp.com", "dave", "Dave");
        when(userMapper.selectOne(any())).thenReturn(null);

        try (MockedStatic<JwtUtils> ignored = mockStatic(JwtUtils.class)) {
            ignored.when(JwtUtils::getTokenValue).thenReturn("t");
            service.loginWithCode("code-6", "state-6");
        }
        org.mockito.ArgumentCaptor<User> captor = org.mockito.ArgumentCaptor.forClass(User.class);
        verify(userMapper).insert(captor.capture());
        User created = captor.getValue();
        assertNotNull(created.getPassword());
        assertTrue(created.getPassword().startsWith("$2"), "应写入不可用于密码登录的随机 BCrypt");
        assertEquals("generic", created.getOauthProvider());
        assertEquals("sub-11", created.getOauthSubject());
    }
}
