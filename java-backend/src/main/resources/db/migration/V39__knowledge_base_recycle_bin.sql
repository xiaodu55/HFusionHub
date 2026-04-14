-- Keep knowledge bases and their documents in a recycle bin for seven days.
ALTER TABLE `knowledge_base`
    ADD COLUMN `recycled_at` DATETIME NULL COMMENT '移入回收站时间' AFTER `updated_at`,
    ADD COLUMN `recycle_expires_at` DATETIME NULL COMMENT '回收站过期时间' AFTER `recycled_at`,
    ADD KEY `idx_knowledge_base_recycle_expires` (`deleted`, `recycle_expires_at`);

-- Repair records left in the old asynchronous "deleting" states and records
-- that were already logically deleted before the recycle-bin fields existed.
UPDATE `knowledge_base`
SET `deleted` = 1,
    `recycled_at` = COALESCE(`updated_at`, NOW()),
    `recycle_expires_at` = DATE_ADD(COALESCE(`updated_at`, NOW()), INTERVAL 7 DAY)
WHERE `recycled_at` IS NULL
  AND (`deleted` = 1 OR `status` IN (2, 3));
