-- Add requestId column for client-side idempotency, plus performance indexes.
-- Apply to existing HFusionHub databases before deploying the V4 chat refactoring.

ALTER TABLE `message`
    ADD COLUMN `request_id` VARCHAR(64) DEFAULT NULL COMMENT '客户端请求幂等ID' AFTER `updated_at`;

ALTER TABLE `message`
    ADD UNIQUE INDEX `uk_request_id` (`request_id`);

ALTER TABLE `message`
    ADD INDEX `idx_conv_created_id` (`conversation_id`, `created_at`, `id`);
