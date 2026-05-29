package com.hfusionhub.service;

import cn.hutool.core.util.RandomUtil;
import cn.hutool.crypto.digest.BCrypt;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.TenantMemberMapper;
import com.hfusionhub.mapper.UserMapper;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Locale;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

/**
 * 通用 OIDC 客户端（Authorization Code 流程）。
 *
 * <p>流程：{@code GET /user/sso/authorize}（302 → IdP 授权端点，携带存入 Redis 的一次性
 * state）→ IdP 回调 {@code GET /user/sso/callback?code&state} → 校验并一次性消费 state
 * （防 CSRF）→ 在令牌端点用 code 换 access_token → 用 Bearer access_token 拉取 userinfo
 * （sub / username / email / name）→ 按 (provider, subject) 找用户：无则按已验证邮箱关联
 * 既有账号，再否则自动开户（role=pending，等待管理员分配身份）→ StpUtil.login 后 302 回
 * 前端并携带 satoken。
 *
 * <p>依赖外部标准 OIDC IdP（Keycloak / Google / Azure AD / 企业微信 等），通过
 * {@code app.oidc.*} 配置（默认关闭）。身份来源为 HTTPS 拉取的 userinfo；
 * id_token 签名校验（JWKS）为可选增强，未默认启用。
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class OidcService {

    private static final String STATE_KEY_PREFIX = "oidc:state:";
    private static final Duration STATE_TTL = Duration.ofMinutes(10);

    private final RestTemplate restTemplate;
    private final RedisTemplate<String, Object> redisTemplate;
    private final UserMapper userMapper;
    private final TenantMemberMapper tenantMemberMapper;
    private final ObjectMapper objectMapper;

    @Value("${app.oidc.enabled:false}")
    private boolean enabled;
    @Value("${app.oidc.provider-name:generic}")
    private String providerName;
    @Value("${app.oidc.authorization-endpoint:}")
    private String authorizationEndpoint;
    @Value("${app.oidc.token-endpoint:}")
    private String tokenEndpoint;
    @Value("${app.oidc.user-info-endpoint:}")
    private String userInfoEndpoint;
    @Value("${app.oidc.client-id:}")
    private String clientId;
    @Value("${app.oidc.client-secret:}")
    private String clientSecret;
    @Value("${app.oidc.redirect-uri:}")
    private String redirectUri;
    @Value("${app.oidc.frontend-redirect-uri:}")
    private String frontendRedirectUri;
    @Value("${app.oidc.scopes:openid profile email}")
    private String scopes;
    @Value("${app.oidc.username-claim:preferred_username}")
    private String usernameClaim;
    @Value("${app.oidc.email-claim:email}")
    private String emailClaim;
    @Value("${app.oidc.name-claim:name}")
    private String nameClaim;
    @Value("${app.oidc.auto-provision:true}")
    private boolean autoProvision;
    @Value("${app.oidc.link-by-email:true}")
    private boolean linkByEmail;

    /** userinfo 中提取的身份信息 */
    public record OidcUserInfo(String subject, String username, String email, String name) {}

    public boolean isEnabled() {
        return enabled;
    }

    public String getProviderName() {
        return providerName;
    }

    public String getFrontendRedirectUri() {
        return frontendRedirectUri;
    }

    /**
     * 校验 OIDC 配置完备性；未启用时抛出业务异常。
     */
    public void ensureConfigured() {
        if (!enabled) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "SSO 登录未启用（app.oidc.enabled=false）");
        }
        if (authorizationEndpoint.isBlank()
                || tokenEndpoint.isBlank()
                || userInfoEndpoint.isBlank()
                || clientId.isBlank()
                || clientSecret.isBlank()
                || redirectUri.isBlank()) {
            throw new BusinessException(
                    StatusCode.BAD_REQUEST,
                    "SSO 未配置完整：需要 authorization/token/userinfo 端点与 client-id/client-secret/redirect-uri");
        }
    }

    /**
     * 生成一次性 state（Redis 落盘，10 分钟 TTL）并拼装授权 URL。
     *
     * @return 302 跳转目标
     */
    public String buildAuthorizationUrl() {
        ensureConfigured();
        String state = RandomUtil.randomString(32);
        redisTemplate.opsForValue().set(STATE_KEY_PREFIX + state, Boolean.TRUE, STATE_TTL);
        return authorizationEndpoint
                + (authorizationEndpoint.contains("?") ? "&" : "?")
                + "response_type=code&client_id=" + enc(clientId)
                + "&redirect_uri=" + enc(redirectUri)
                + "&scope=" + enc(scopes)
                + "&state=" + state;
    }

    /**
     * 授权码换取令牌 + 拉取 userinfo，返回 IdP 侧身份。
     *
     * @param code  IdP 回调下发的授权码
     * @param state IdP 原样带回的 state（一次性校验）
     */
    public OidcUserInfo fetchUserInfo(String code, String state) {
        ensureConfigured();
        consumeState(state);

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type", "authorization_code");
        form.add("code", code);
        form.add("redirect_uri", redirectUri);
        form.add("client_id", clientId);
        form.add("client_secret", clientSecret);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        HttpEntity<MultiValueMap<String, String>> request = new HttpEntity<>(form, headers);

        String accessToken;
        try {
            JsonNode tokenResponse = restTemplate.postForObject(tokenEndpoint, request, JsonNode.class);
            if (tokenResponse == null) {
                throw new BusinessException(StatusCode.LOGIN_ERROR, "SSO 令牌端点无响应");
            }
            accessToken = tokenResponse.path("access_token").asText(null);
            if (accessToken == null || accessToken.isBlank()) {
                String error = tokenResponse.path("error").asText("unknown");
                log.warn("SSO_TOKEN_EXCHANGE_FAILED error={}", error);
                throw new BusinessException(StatusCode.LOGIN_ERROR, "SSO 授权码换取令牌失败（" + error + "）");
            }
        } catch (RestClientException e) {
            log.warn("SSO_TOKEN_EXCHANGE_ERROR", e);
            throw new BusinessException(StatusCode.LOGIN_ERROR, "SSO 令牌端点请求失败");
        }

        HttpHeaders userHeaders = new HttpHeaders();
        userHeaders.setBearerAuth(accessToken);
        JsonNode info;
        try {
            info = restTemplate
                    .exchange(userInfoEndpoint, HttpMethod.GET, new HttpEntity<>(userHeaders), JsonNode.class)
                    .getBody();
        } catch (RestClientException e) {
            log.warn("SSO_USERINFO_ERROR", e);
            throw new BusinessException(StatusCode.LOGIN_ERROR, "SSO 用户信息获取失败");
        }
        if (info == null) {
            throw new BusinessException(StatusCode.LOGIN_ERROR, "SSO 用户信息无响应");
        }

        String subject = info.path("sub").asText(null);
        if (subject == null || subject.isBlank()) {
            throw new BusinessException(StatusCode.LOGIN_ERROR, "SSO userinfo 缺少 sub 声明");
        }
        String username = info.path(usernameClaim).asText(null);
        String name = info.path(nameClaim).asText(null);
        if (username == null || username.isBlank()) {
            username = subject;
        }
        return new OidcUserInfo(subject, username, info.path(emailClaim).asText(null), name == null || name.isBlank() ? username : name);
    }

    /**
     * 完整 SSO 登录：校验 state → 换 token → 拉 userinfo → 解析/关联/开户 → Sa-Token 登录。
     *
     * @return satoken
     */
    @Transactional
    public String loginWithCode(String code, String state) {
        OidcUserInfo info = fetchUserInfo(code, state);
        User user = resolveUser(info);
        user.setLastLoginTime(LocalDateTime.now());
        userMapper.updateById(user);
        JwtUtils.login(user.getId());
        log.info("SSO_LOGIN_SUCCESS userId={} provider={} subject={}", user.getId(), providerName, info.subject());
        return JwtUtils.getTokenValue();
    }

    /** 校验并一次性消费 state（防 CSRF 回调）。 */
    private void consumeState(String state) {
        if (state == null || state.isBlank()) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "SSO 回调缺少 state 参数");
        }
        Boolean present = Boolean.TRUE.equals(redisTemplate.opsForValue().get(STATE_KEY_PREFIX + state));
        redisTemplate.delete(STATE_KEY_PREFIX + state);
        if (!Boolean.TRUE.equals(present)) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "SSO state 无效或已过期，请重新发起登录");
        }
    }

    /**
     * 解析 IdP 身份到本地用户：
     * ① (provider, subject) 精确匹配；② 否则按已验证邮箱关联既有账号；
     * ③ 否则 autoProvision 自动开户（role=pending）或拒绝。
     */
    private User resolveUser(OidcUserInfo info) {
        User bySubject = userMapper.selectOne(new LambdaQueryWrapper<User>()
                .eq(User::getOauthProvider, providerName)
                .eq(User::getOauthSubject, info.subject()));
        if (bySubject != null) {
            return rejectIfDisabled(bySubject);
        }

        String email = info.email() == null ? null : info.email().toLowerCase(Locale.ROOT);
        if (linkByEmail && email != null && !email.isBlank()) {
            User byEmail = userMapper.selectOne(new LambdaQueryWrapper<User>().eq(User::getEmail, email));
            if (byEmail != null) {
                if (byEmail.getOauthSubject() != null) {
                    // 该邮箱已被另一 IdP 主体绑定——拒绝，避免身份混淆
                    throw new BusinessException(StatusCode.FORBIDDEN, "该邮箱已绑定其他 SSO 身份，请联系管理员");
                }
                byEmail.setOauthProvider(providerName);
                byEmail.setOauthSubject(info.subject());
                userMapper.updateById(byEmail);
                log.info(
                        "SSO_LINKED_BY_EMAIL userId={} provider={} subject={}",
                        byEmail.getId(),
                        providerName,
                        info.subject());
                return rejectIfDisabled(byEmail);
            }
        }

        if (!autoProvision) {
            throw new BusinessException(StatusCode.FORBIDDEN, "SSO 账号未绑定本地用户，请联系管理员开通");
        }
        return provisionUser(info, email);
    }

    private User provisionUser(OidcUserInfo info, String email) {
        String base = (info.username() != null && !info.username().isBlank()) ? info.username() : "sso_" + info.subject();
        String username = base;
        if (userMapper.selectCount(new LambdaQueryWrapper<User>().eq(User::getUsername, username)) > 0) {
            username = base + "_" + RandomUtil.randomString(6);
        }

        User user = new User();
        user.setUsername(username);
        // password 列 NOT NULL——写入不可用于密码登录的随机 BCrypt
        user.setPassword(BCrypt.hashpw(RandomUtil.randomString(32)));
        user.setNickname(info.name() != null ? info.name() : username);
        user.setEmail(email);
        user.setRole(CommonConstants.ROLE_PENDING);
        user.setStatus(CommonConstants.USER_STATUS_NORMAL);
        user.setTenantId(CommonConstants.DEFAULT_TENANT_ID);
        user.setOauthProvider(providerName);
        user.setOauthSubject(info.subject());
        userMapper.insert(user);

        TenantMember member = new TenantMember();
        member.setTenantId(CommonConstants.DEFAULT_TENANT_ID);
        member.setUserId(user.getId());
        member.setRole("member");
        tenantMemberMapper.insert(member);

        log.info(
                "SSO_PROVISIONED userId={} provider={} subject={} username={}",
                user.getId(),
                providerName,
                info.subject(),
                username);
        return user;
    }

    private User rejectIfDisabled(User user) {
        if (user.getStatus() != null && user.getStatus() == 1) {
            throw new BusinessException(StatusCode.USER_DISABLED, "用户已被禁用");
        }
        return user;
    }

    private static String enc(String value) {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8);
    }
}
