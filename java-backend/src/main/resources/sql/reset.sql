-- =====================================================
-- HFusionHub 数据库重置脚本
-- 仅保留默认管理员账号，清空所有业务数据
-- =====================================================

-- 确保使用 UTF-8 字符集
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

USE `hfusionhub`;

-- 禁用外键检查
SET FOREIGN_KEY_CHECKS = 0;

-- 清空所有表
TRUNCATE TABLE `message`;
TRUNCATE TABLE `conversation`;
TRUNCATE TABLE `document`;
TRUNCATE TABLE `knowledge_base`;
TRUNCATE TABLE `tool`;
TRUNCATE TABLE `sys_user`;

-- 启用外键检查
SET FOREIGN_KEY_CHECKS = 1;

-- 插入默认管理员用户
-- 密码: admin123 (BCrypt加密)
INSERT INTO `sys_user` (`username`, `password`, `nickname`, `role`, `status`)
VALUES ('admin', '$2a$10$hLsOQw/IutrOdOFEdZL2JO/0F0DQHtO6ioO3g0R4v.2dOeqoHcENC', _utf8mb4'管理员', 'admin', 0);

-- 验证
SELECT '数据库重置完成！' AS message;
SELECT COUNT(*) AS user_count FROM `sys_user`;
