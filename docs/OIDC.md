# SSO / OIDC 单点登录

通用 OIDC 客户端（Authorization Code 流程），对接任意标准 OIDC 身份提供商
（IdP：Keycloak / Google / Azure AD / 企业微信 等）。**默认关闭**，通过
`app.oidc.*` 环境变量启用（见 [ENVIRONMENT.md](ENVIRONMENT.md)）。

## 流程

```
登录页「SSO 登录」 → GET /user/sso/authorize
  → 后端生成一次性 state（Redis 落盘，10 分钟 TTL）→ 302 到 IdP 授权端点
IdP 登录并授权 → 302 回 GET /user/sso/callback?code&state
  → 校验并一次性消费 state（防 CSRF）
  → 令牌端点 code 换 access_token（client_secret 认证）
  → userinfo 端点（Bearer）取 sub / preferred_username / email / name
  → 按 (provider, subject) 找本地用户
      ├─ 命中 → 直接登录（禁用账号拒绝）
      ├─ 未命中且邮箱命中既有账号 → 关联该账号（link-by-email）
      └─ 否则 auto-provision 自动开户（role=pending，等管理员分配身份）
  → StpUtil.login → 302 回前端 {frontend-redirect-uri}?token=<satoken>
前端 /sso/callback 落地页 → 落库 satoken → 拉取用户信息 → 进入工作台
```

## 配置（环境变量，均在 `java-backend` 侧）

| 变量 | 必填 | 说明 |
|---|---|---|
| `OIDC_ENABLED` | 是 | `true` 才暴露登录入口；`false` 时 `/user/sso/*` 返回 400 |
| `OIDC_PROVIDER_NAME` | 否 | 存入 `sys_user.oauth_provider` 的标识，默认 `generic` |
| `OIDC_AUTHORIZATION_ENDPOINT` | 是 | IdP 授权端点 |
| `OIDC_TOKEN_ENDPOINT` | 是 | IdP 令牌端点 |
| `OIDC_USERINFO_ENDPOINT` | 是 | IdP 用户信息端点 |
| `OIDC_CLIENT_ID` | 是 | 在 IdP 注册的本应用 client id |
| `OIDC_CLIENT_SECRET` | 是 | 对应 client secret（**视为机密**） |
| `OIDC_REDIRECT_URI` | 是 | 本应用回调地址，需在 IdP 授权回调白名单注册（如 `https://your-domain/api/user/sso/callback`） |
| `OIDC_FRONTEND_REDIRECT_URI` | 否 | 登录成功后前端落地地址（携带 `?token=`），如 `https://your-domain/#/sso/callback`；留空则回调直接返回 JSON |
| `OIDC_SCOPES` | 否 | 默认 `openid profile email` |
| `OIDC_USERNAME_CLAIM` / `OIDC_EMAIL_CLAIM` / `OIDC_NAME_CLAIM` | 否 | userinfo 中用户名/邮箱/昵称声明名，默认 `preferred_username` / `email` / `name` |
| `OIDC_AUTO_PROVISION` | 否 | 首次 SSO 登录是否自动开户，默认 `true`（role=`pending`） |
| `OIDC_LINK_BY_EMAIL` | 否 | 是否允许按已验证邮箱关联既有账号，默认 `true` |

### 启用步骤

1. 在 IdP 注册一个 Web 应用，回调地址填 `OIDC_REDIRECT_URI`，取得 client id / secret。
2. 给 Java 后端注入上述环境变量（`OIDC_ENABLED=true` 等），重启 Java。
3. 登录页出现「{provider} 单点登录」按钮（登录页挂载时查询 `/user/sso/providers`）。
4. 管理员在「管理 → 用户」为 SSO 开户的 `pending` 账号分配身份（与注册账号一致）。

## 安全说明

- **state 防 CSRF**：回调携带的 state 必须是授权步骤中落盘的那一个，且一次性消费。
- **身份来源**：以 HTTPS 拉取的 userinfo 为权威（sub 为跨 IdP 稳定标识）。
  id_token 的 JWKS 签名校验为可选增强，当前未默认启用——生产接入时建议在 IdP
  侧仅允许受信 client，并确认 userinfo 端点经 TLS 暴露。
- **密码隔离**：SSO 开户账号写入随机 BCrypt 口令，无法通过用户名密码登录；
  同邮箱关联既有账号时，`oauth_provider/oauth_subject` 被占用则拒绝（防身份混淆）。
- **禁用账号**：`status=1` 的账号即使 IdP 校验通过也会拒绝登录。
- **回跳 token 经 URL 传递**：默认 `frontend-redirect-uri` 使用前端 hash 路由
  （`#/sso/callback`），satoken 不会出现在 path 中；如改用 query 路由，请确认
  浏览器历史/日志可接受该令牌出现在 URL。

## 数据库

- Flyway **V60** 为 `sys_user` 增加 `oauth_provider` / `oauth_subject` 列与
  `uk_oauth_provider_subject` 唯一索引。升级后既有账号不受影响。

## 测试

`OidcServiceTest`（9 例）覆盖：未启用拒绝、授权 URL 参数、state 缺失/消费、
新用户自动开户并登录、既有 subject 直接登录、禁用账号拒绝、令牌交换失败、
userinfo 缺 sub、开户写入随机口令。`SsoControllerTest`（4 例）覆盖提供方信息
与 302 重定向。
