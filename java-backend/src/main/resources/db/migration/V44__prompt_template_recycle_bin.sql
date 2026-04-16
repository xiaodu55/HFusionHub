-- Keep answer plans in a recycle bin for seven days before physical deletion.
ALTER TABLE `prompt_template`
    ADD COLUMN `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '0-正常，1-回收站' AFTER `version`,
    ADD COLUMN `recycled_at` DATETIME NULL COMMENT '移入回收站时间' AFTER `deleted`,
    ADD COLUMN `recycle_expires_at` DATETIME NULL COMMENT '回收站过期时间' AFTER `recycled_at`;

ALTER TABLE `prompt_template`
    DROP INDEX `uk_prompt_template_user_name`,
    ADD UNIQUE KEY `uk_prompt_template_user_name_deleted` (`user_id`, `name`, `deleted`),
    ADD KEY `idx_prompt_template_recycle_expires` (`deleted`, `recycle_expires_at`);
