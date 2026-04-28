-- Fix: kb_share and app_api_key were created without a tenant_id column
-- (V53 / V52), but the MyBatis-Plus tenant-line interceptor appends
-- `tenant_id = ?` to every non-ignored table, producing
-- "Unknown column 'tenant_id'" SQL errors. Add the column and backfill
-- from the owning resource/user.

-- kb_share → derive tenant from the shared knowledge base (fallback: owner user)
ALTER TABLE `kb_share`
    ADD COLUMN `tenant_id` BIGINT NULL COMMENT '所属租户ID' AFTER `id`,
    ADD KEY `idx_kb_share_tenant` (`tenant_id`);

UPDATE `kb_share` s
    JOIN `knowledge_base` kb ON kb.id = s.knowledge_base_id
SET s.tenant_id = kb.tenant_id
WHERE s.tenant_id IS NULL;

UPDATE `kb_share` s
    JOIN `sys_user` u ON u.id = s.owner_user_id
SET s.tenant_id = u.tenant_id
WHERE s.tenant_id IS NULL;

-- app_api_key → derive tenant from the owning app (fallback: app owner user)
ALTER TABLE `app_api_key`
    ADD COLUMN `tenant_id` BIGINT NULL COMMENT '所属租户ID' AFTER `id`,
    ADD KEY `idx_app_api_key_tenant` (`tenant_id`);

UPDATE `app_api_key` k
    JOIN `app` a ON a.id = k.app_id
SET k.tenant_id = a.tenant_id
WHERE k.tenant_id IS NULL;

UPDATE `app_api_key` k
    JOIN `app` a ON a.id = k.app_id
    JOIN `sys_user` u ON u.id = a.user_id
SET k.tenant_id = u.tenant_id
WHERE k.tenant_id IS NULL;
