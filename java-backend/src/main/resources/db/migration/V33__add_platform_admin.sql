-- HFusionHub V33 — Add platform_admin flag to sys_user
-- Required by User entity (platformAdmin field) but missing from earlier migrations.

ALTER TABLE sys_user
    ADD COLUMN platform_admin TINYINT NOT NULL DEFAULT 0
    COMMENT '平台管理员标记：0-普通用户，1-平台管理员（跨租户）'
    AFTER tenant_id;

-- Existing admin user (role='admin') should be a platform admin
UPDATE sys_user SET platform_admin = 1 WHERE role = 'admin';
