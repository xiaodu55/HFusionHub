-- V60: SSO/OIDC 外部身份绑定（oauth_provider + oauth_subject）
-- 供通用 OIDC 客户端（/user/sso/*）将 IdP 的 sub 声明映射到 sys_user。
-- (provider, subject) 唯一，防止同一 IdP 身份被重复建号 / 被他人占用邮箱顶替。
ALTER TABLE sys_user
    ADD COLUMN oauth_provider VARCHAR(32) DEFAULT NULL COMMENT 'OIDC provider name (e.g. generic, wecom)',
    ADD COLUMN oauth_subject  VARCHAR(255) DEFAULT NULL COMMENT 'OIDC subject (sub) claim from the provider',
    ADD UNIQUE KEY uk_oauth_provider_subject (oauth_provider, oauth_subject);
