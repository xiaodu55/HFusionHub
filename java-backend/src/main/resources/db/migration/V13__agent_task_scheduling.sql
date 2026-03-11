-- =====================================================
-- HFusionHub V13 — Agent 异步任务调度与可靠恢复
-- 新增: agent_status_event (状态事件/SSE推送), agent_recovery_event (恢复审计)
-- 变更: agent_task (死信), agent_run (队列/租约/心跳)
-- =====================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ── agent_task: 死信状态附加列 ──────────────────────────
ALTER TABLE `agent_task`
    ADD COLUMN `dead_letter_reason` VARCHAR(500) DEFAULT NULL COMMENT '死信原因(重试耗尽)' AFTER `current_run_id`,
    ADD COLUMN `dead_letter_at`     DATETIME     DEFAULT NULL COMMENT '死信时间' AFTER `dead_letter_reason`;

ALTER TABLE `agent_task`
    ADD INDEX `idx_task_status_updated` (`status`, `updated_at`);

-- ── agent_run: 队列调度 + 租约 + 心跳 + 派发计数 ──────────
ALTER TABLE `agent_run`
    ADD COLUMN `scheduled_at`     DATETIME     DEFAULT NULL COMMENT '计划执行时间(重试退避; NULL=立即可执行)' AFTER `status`,
    ADD COLUMN `lease_holder`     VARCHAR(64)  DEFAULT NULL COMMENT '租约持有者(worker实例ID 或 stream:xx)' AFTER `scheduled_at`,
    ADD COLUMN `lease_expires_at` DATETIME     DEFAULT NULL COMMENT '租约过期时间' AFTER `lease_holder`,
    ADD COLUMN `heartbeat_at`     DATETIME     DEFAULT NULL COMMENT '最近心跳时间' AFTER `lease_expires_at`,
    ADD COLUMN `dispatch_count`   INT          NOT NULL DEFAULT 1 COMMENT '物理派发次数(孤儿重派时递增)' AFTER `heartbeat_at`;

ALTER TABLE `agent_run`
    ADD INDEX `idx_run_queue`  (`status`, `scheduled_at`),
    ADD INDEX `idx_run_lease`  (`lease_expires_at`),
    ADD INDEX `idx_run_holder` (`lease_holder`);

-- ── agent_status_event: SSE 推送 + 审计 ─────────────────
CREATE TABLE IF NOT EXISTS `agent_status_event` (
    `id`         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '事件ID(单调递增,SSE断点续传)',
    `task_id`    BIGINT       NOT NULL                COMMENT '任务ID',
    `run_id`     BIGINT       DEFAULT NULL            COMMENT '运行ID(可能为空)',
    `event_type` VARCHAR(40)  NOT NULL                COMMENT 'QUEUED|RUN_STARTED|STEP_RECORDED|RETRY_SCHEDULED|RUN_SUCCEEDED|RUN_FAILED|RUN_TIMED_OUT|CANCELLED|DEAD_LETTERED|RECOVERED|APPROVAL_REQUIRED|APPROVAL_DECIDED',
    `status`     VARCHAR(20)  DEFAULT NULL            COMMENT '事件发生时任务状态',
    `payload`    JSON         DEFAULT NULL            COMMENT '附加载荷(错误码/尝试次数/下次重试时间等)',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    INDEX `idx_ase_task` (`task_id`, `id`),
    CONSTRAINT `fk_ase_task` FOREIGN KEY (`task_id`) REFERENCES `agent_task` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent状态事件表(SSE推送与审计)';

-- ── agent_recovery_event: 恢复动作审计 ───────────────────
CREATE TABLE IF NOT EXISTS `agent_recovery_event` (
    `id`         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '事件ID',
    `run_id`     BIGINT       NOT NULL                COMMENT '运行ID',
    `task_id`    BIGINT       NOT NULL                COMMENT '任务ID',
    `event_type` VARCHAR(40)  NOT NULL                COMMENT 'ORPHAN_RECLAIMED|WATCHDOG_TIMED_OUT|SUPERSEDED_REJECTED|STALE_CALLBACK_REJECTED|DEAD_LETTERED|RESTART_RECOVERED',
    `detail`     VARCHAR(1000) DEFAULT NULL           COMMENT '恢复详情',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    INDEX `idx_are_run` (`run_id`),
    INDEX `idx_are_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent恢复审计表';
