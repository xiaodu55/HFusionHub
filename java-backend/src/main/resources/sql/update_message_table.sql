-- 更新 message 表，添加 updated_at 字段
ALTER TABLE `message`
ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间' AFTER `created_at`;

-- 更新现有记录的 updated_at 为 created_at
UPDATE `message` SET `updated_at` = `created_at` WHERE `updated_at` IS NULL;