-- Keep document records and source files in a recycle bin for seven days.
ALTER TABLE `document`
    ADD COLUMN `recycled_at` DATETIME NULL COMMENT '移入回收站时间' AFTER `processed_at`,
    ADD COLUMN `recycle_expires_at` DATETIME NULL COMMENT '回收站过期时间' AFTER `recycled_at`,
    ADD KEY `idx_document_recycle_expires` (`deleted`, `recycle_expires_at`);
