-- HFusionHub V27 — Agent tool governance: durable one-time execution token + distributed trace correlation + role record.
-- A durable, MySQL-backed one-shot execution token issued at approval time.  It survives Python
-- restart, prevents double-execution on replay of the /decide call, and links the approval to its
-- distributed trace for audit.
ALTER TABLE `agent_approval`
    ADD COLUMN `trace_id`            VARCHAR(64)  DEFAULT NULL COMMENT '分布式追踪 ID（关联 agent run / step）' AFTER `run_id`,
    ADD COLUMN `user_role`           VARCHAR(20)  DEFAULT 'user' COMMENT '审批目标用户角色（策略判定依据）' AFTER `user_id`,
    ADD COLUMN `execution_token`     VARCHAR(64)  DEFAULT NULL COMMENT '一次性执行令牌（批准时签发）' AFTER `tool_input_hash`,
    ADD COLUMN `execution_token_status` VARCHAR(16) DEFAULT 'none' COMMENT 'none|issued|consumed|revoked' AFTER `execution_token`,
    ADD COLUMN `execution_token_issued_at` DATETIME DEFAULT NULL COMMENT '令牌签发时间' AFTER `execution_token_status`,
    ADD COLUMN `execution_token_consumed_at` DATETIME DEFAULT NULL COMMENT '令牌消耗时间' AFTER `execution_token_issued_at`;

CREATE INDEX `idx_approval_token_status` ON `agent_approval` (`execution_token`, `execution_token_status`);