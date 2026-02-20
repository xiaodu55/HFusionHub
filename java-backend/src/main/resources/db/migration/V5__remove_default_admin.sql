-- =====================================================
-- HFusionHub V5 — 移除默认管理员 (Flyway)
-- =====================================================
-- 安全删除 V1 迁移中创建的默认 admin/admin123 账户。
-- 仅当密码哈希与已知默认值完全匹配时才删除，避免误删已修改密码的管理员。
-- 新管理员通过 AdminInitializer 根据 ADMIN_PASSWORD 环境变量创建。
-- =====================================================

DELETE FROM `sys_user`
WHERE `username` = 'admin'
  AND `password` = '$2a$10$hLsOQw/IutrOdOFEdZL2JO/0F0DQHtO6ioO3g0R4v.2dOeqoHcENC';
