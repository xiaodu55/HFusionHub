-- =====================================================
-- HFusionHub V11 — Agent 审批记录表
-- =====================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `agent_approval` (
    `id`                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '审批记录ID',
    `approval_id`       VARCHAR(36)  NOT NULL                COMMENT '审批UUID',
    `task_id`           BIGINT       NOT NULL                COMMENT '关联任务ID',
    `run_id`            BIGINT       NOT NULL                COMMENT '关联运行ID',
    `user_id`           BIGINT       NOT NULL                COMMENT '审批目标用户ID',
    `tool_name`         VARCHAR(50)  NOT NULL                COMMENT '工具名称',
    `tool_input_hash`   VARCHAR(64)  NOT NULL                COMMENT '工具参数SHA-256摘要',
    `arguments_summary` TEXT         NOT NULL                COMMENT '参数摘要(脱敏)',
    `status`            VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT 'pending|approved|denied|expired',
    `decided_by`        BIGINT       DEFAULT NULL            COMMENT '审批人用户ID',
    `decided_at`        DATETIME     DEFAULT NULL            COMMENT '审批决定时间',
    `reason`            TEXT         DEFAULT NULL            COMMENT '审批决定原因',
    `expires_at`        DATETIME     NOT NULL                COMMENT '过期时间(创建+5分钟)',
    `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_approval_id` (`approval_id`),
    INDEX `idx_approval_task` (`task_id`),
    INDEX `idx_approval_run` (`run_id`),
    INDEX `idx_approval_status` (`status`),
    INDEX `idx_approval_expires` (`status`, `expires_at`),
    CONSTRAINT `fk_approval_task` FOREIGN KEY (`task_id`) REFERENCES `agent_task` (`id`),
    CONSTRAINT `fk_approval_run` FOREIGN KEY (`run_id`) REFERENCES `agent_run` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent审批记录表';
