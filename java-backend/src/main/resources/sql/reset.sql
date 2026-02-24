-- =====================================================
-- HFusionHub 数据库重置脚本
-- 清空业务数据与用户数据；管理员由 ADMIN_PASSWORD 重新引导创建
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

-- Admin users are bootstrapped by AdminInitializer from ADMIN_PASSWORD.
-- Do not seed a default admin password in SQL scripts.

-- 验证
SELECT '数据库重置完成！' AS message;
SELECT COUNT(*) AS user_count FROM `sys_user`;
