-- Outbox-based asynchronous deletion tasks for knowledge bases and documents.
-- Apply to existing HFusionHub databases before deploying the V3 deletion service.

CREATE TABLE IF NOT EXISTS `deletion_task` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '任务ID',
    `task_type` VARCHAR(32) NOT NULL COMMENT 'KB_DELETE / DOCUMENT_DELETE',
    `target_id` BIGINT NOT NULL COMMENT '知识库ID 或 文档ID',
    `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        COMMENT 'PENDING / PROCESSING / RETRYING / COMPLETED / FAILED',
    `step` VARCHAR(64) DEFAULT NULL COMMENT '当前执行步骤名称',
    `step_index` INT NOT NULL DEFAULT 0 COMMENT '当前步骤索引 (0-based)',
    `max_retries` INT NOT NULL DEFAULT 5 COMMENT '最大重试次数',
    `retry_count` INT NOT NULL DEFAULT 0 COMMENT '已重试次数',
    `error_message` VARCHAR(2000) DEFAULT NULL COMMENT '失败原因',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_status_created` (`status`, `created_at`),
    KEY `idx_target` (`task_type`, `target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='异步删除任务';
