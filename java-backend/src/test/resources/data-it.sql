-- ============================================================
-- it profile 测试主体种子（从 schema-h2.sql 提取，MySQL 方言，
-- ON DUPLICATE KEY 幂等可重放；在 Flyway 迁移之后执行）
-- ============================================================

INSERT INTO role_permission (role, permission) VALUES ('owner', 'kb:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'kb:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'kb:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'conversation:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'conversation:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'plugin:install') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'plugin:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'member:invite') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'member:remove') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'member:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'tenant:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'tenant:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'billing:view') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'quota:view') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'quota:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'kb:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'kb:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'kb:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'conversation:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'conversation:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'plugin:install') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'plugin:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'member:invite') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'member:remove') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'member:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'quota:view') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'billing:view') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('member', 'kb:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('member', 'kb:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('member', 'conversation:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('member', 'plugin:install') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('viewer', 'kb:read') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('viewer', 'conversation:read') ON DUPLICATE KEY UPDATE role = role;

-- V34 —tenant_audit_log (global, not tenant-scoped)
CREATE TABLE IF NOT EXISTS tenant_audit_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    operator_id BIGINT NOT NULL,
    from_tenant BIGINT NOT NULL,
    to_tenant   BIGINT NOT NULL,
    action      VARCHAR(500) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Add tenant_id to sys_user (H2-compatible ALTER)

-- Insert default tenant for tests
INSERT INTO tenant (id, name, slug, plan_tier, status) VALUES
    (1, 'Default', 'default', 'enterprise', 'active')
    ON DUPLICATE KEY UPDATE slug = 'default';

-- Insert default user for tests (FK target for conversation.user_id etc.)
INSERT INTO sys_user (id, username, password, nickname, role, status, tenant_id)
    VALUES (1, 'default-user', 'test', 'Default', 'user', 0, 1)
    ON DUPLICATE KEY UPDATE nickname = 'Default';

-- Add tenant_id column to existing H2 tables (only those created above)

-- 补充：it 环境的默认测试用户（ conversation.user_id 等 FK 目标 ）
INSERT INTO sys_user (id, username, password, nickname, role, status, tenant_id)
    VALUES (2, 'it-user', 'test', 'IT User', 'user', 0, 1)
    ON DUPLICATE KEY UPDATE nickname = 'IT User';
