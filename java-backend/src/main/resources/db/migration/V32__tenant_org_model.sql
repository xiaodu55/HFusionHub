-- HFusionHub V32 — Tenant, Organization Member & Role-Permission Model
-- Adds tenant boundary to every user-owned table.  Backfills a default tenant
-- so existing single-user deployments continue unchanged.

-- =====================================================
-- 1. Core tenant tables
-- =====================================================
CREATE TABLE tenant (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    name        VARCHAR(100) NOT NULL COMMENT '租户名称',
    slug        VARCHAR(50)  NOT NULL COMMENT '唯一标识符，用于导出文件名',
    plan_tier   VARCHAR(20)  NOT NULL DEFAULT 'free' COMMENT 'free|pro|enterprise',
    status      VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active|suspended|deleted',
    created_by  BIGINT       DEFAULT NULL COMMENT 'platform admin who created it',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted     TINYINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_tenant_slug (slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户表';

CREATE TABLE tenant_member (
    id          BIGINT      NOT NULL AUTO_INCREMENT,
    tenant_id   BIGINT      NOT NULL COMMENT 'FK to tenant.id',
    user_id     BIGINT      NOT NULL COMMENT 'FK to sys_user.id',
    role        VARCHAR(20) NOT NULL DEFAULT 'member' COMMENT 'owner|admin|member|viewer',
    joined_at   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted     TINYINT     NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_tenant_member (tenant_id, user_id),
    INDEX idx_member_user (user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    FOREIGN KEY (user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户成员表';

-- =====================================================
-- 2. Role-permission mapping
-- =====================================================
CREATE TABLE role_permission (
    role        VARCHAR(20)  NOT NULL,
    permission  VARCHAR(100) NOT NULL,
    PRIMARY KEY (role, permission)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色权限映射';

-- Seed permissions per role
INSERT INTO role_permission (role, permission) VALUES
('owner',   'kb:create'), ('owner', 'kb:delete'), ('owner', 'kb:manage'),
('owner',   'conversation:create'), ('owner', 'conversation:delete'),
('owner',   'plugin:install'), ('owner', 'plugin:manage'),
('owner',   'member:invite'), ('owner', 'member:remove'), ('owner', 'member:manage'),
('owner',   'tenant:manage'), ('owner', 'tenant:delete'),
('owner',   'billing:view'), ('owner', 'quota:view'), ('owner', 'quota:manage'),
('admin',   'kb:create'), ('admin', 'kb:delete'), ('admin', 'kb:manage'),
('admin',   'conversation:create'), ('admin', 'conversation:delete'),
('admin',   'plugin:install'), ('admin', 'plugin:manage'),
('admin',   'member:invite'), ('admin', 'member:remove'), ('admin', 'member:manage'),
('admin',   'quota:view'), ('admin', 'billing:view'),
('member',  'kb:create'), ('member', 'kb:manage'),
('member',  'conversation:create'),
('member',  'plugin:install'),
('viewer',  'kb:read'), ('viewer', 'conversation:read');

-- =====================================================
-- 3. Add tenant_id to sys_user
-- =====================================================
ALTER TABLE sys_user ADD COLUMN tenant_id BIGINT DEFAULT NULL COMMENT '所属租户ID'
    AFTER last_login_ip;
ALTER TABLE sys_user ADD INDEX idx_user_tenant (tenant_id);

-- =====================================================
-- 4. Create default tenant + assign all existing users
-- =====================================================
INSERT INTO tenant (id, name, slug, plan_tier, status) VALUES
    (1, '默认租户', 'default', 'enterprise', 'active');

UPDATE sys_user SET tenant_id = 1 WHERE tenant_id IS NULL;

-- Make tenant_id NOT NULL after backfill
ALTER TABLE sys_user MODIFY COLUMN tenant_id BIGINT NOT NULL COMMENT '所属租户ID';

INSERT INTO tenant_member (tenant_id, user_id, role)
    SELECT 1, id, 'owner' FROM sys_user;

-- =====================================================
-- 5. Add tenant_id to all resource tables
-- =====================================================
ALTER TABLE knowledge_base ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE conversation    ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE agent_task      ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE memory_entry    ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE prompt_template ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE prompt_test_set ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE prompt_test_set_run ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE agent_evaluation_dataset ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE agent_alert_rule ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE agent_alert_event ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;
ALTER TABLE plugin          ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER installed_by;
ALTER TABLE plugin_audit_log ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER operator_id;
ALTER TABLE agent_approval  ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER user_id;

-- =====================================================
-- 6. Backfill tenant_id on all resource tables
-- =====================================================
UPDATE knowledge_base SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = knowledge_base.user_id);
UPDATE conversation    SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = conversation.user_id);
UPDATE agent_task      SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = agent_task.user_id);
UPDATE memory_entry    SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = memory_entry.user_id);
UPDATE prompt_template SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = prompt_template.user_id);
UPDATE prompt_test_set SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = prompt_test_set.user_id);
UPDATE prompt_test_set_run SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = prompt_test_set_run.user_id);
UPDATE agent_evaluation_dataset SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = agent_evaluation_dataset.user_id);
UPDATE agent_alert_rule SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = agent_alert_rule.user_id) WHERE user_id IS NOT NULL;
UPDATE agent_alert_event SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = agent_alert_event.user_id) WHERE user_id IS NOT NULL;
UPDATE plugin          SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = plugin.installed_by);
UPDATE plugin_audit_log SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = plugin_audit_log.operator_id);
UPDATE agent_approval  SET tenant_id = (SELECT u.tenant_id FROM sys_user u WHERE u.id = agent_approval.user_id);

-- Document inherits tenant via knowledge_base
ALTER TABLE document ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER knowledge_base_id;
UPDATE document SET tenant_id = (SELECT kb.tenant_id FROM knowledge_base kb WHERE kb.id = document.knowledge_base_id);

-- Message inherits tenant via conversation
ALTER TABLE message ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER conversation_id;
UPDATE message SET tenant_id = (SELECT c.tenant_id FROM conversation c WHERE c.id = message.conversation_id);

-- agent_run inherits tenant via agent_task
ALTER TABLE agent_run ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER task_id;
UPDATE agent_run SET tenant_id = (SELECT t.tenant_id FROM agent_task t WHERE t.id = agent_run.task_id);

-- agent_step inherits tenant via agent_run → agent_task
ALTER TABLE agent_step ADD COLUMN tenant_id BIGINT DEFAULT NULL AFTER run_id;
UPDATE agent_step s JOIN agent_run r ON s.run_id = r.id
    SET s.tenant_id = r.tenant_id;

-- =====================================================
-- 7. Make tenant_id NOT NULL after backfill + add indexes
-- =====================================================
ALTER TABLE knowledge_base MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE conversation    MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE agent_task      MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE memory_entry    MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE prompt_template MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE prompt_test_set MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE prompt_test_set_run MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE agent_evaluation_dataset MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE plugin          MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE agent_approval  MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE document        MODIFY COLUMN tenant_id BIGINT NOT NULL;
ALTER TABLE message         MODIFY COLUMN tenant_id BIGINT NOT NULL;

-- Index on every tenant_id for query performance
ALTER TABLE knowledge_base ADD INDEX idx_kb_tenant (tenant_id);
ALTER TABLE conversation    ADD INDEX idx_conv_tenant (tenant_id);
ALTER TABLE agent_task      ADD INDEX idx_task_tenant (tenant_id);
ALTER TABLE memory_entry    ADD INDEX idx_memory_tenant (tenant_id);
ALTER TABLE prompt_template ADD INDEX idx_pt_tenant (tenant_id);
ALTER TABLE document        ADD INDEX idx_doc_tenant (tenant_id);
ALTER TABLE message         ADD INDEX idx_msg_tenant (tenant_id);
ALTER TABLE agent_run       ADD INDEX idx_run_tenant (tenant_id);
ALTER TABLE agent_step      ADD INDEX idx_step_tenant (tenant_id);
ALTER TABLE plugin          ADD INDEX idx_plugin_tenant (tenant_id);
ALTER TABLE plugin_audit_log ADD INDEX idx_pal_tenant (tenant_id);
ALTER TABLE agent_approval  ADD INDEX idx_approval_tenant (tenant_id);
