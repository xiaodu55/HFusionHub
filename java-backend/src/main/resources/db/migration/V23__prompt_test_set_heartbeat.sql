-- Prompt Test Set Run — heartbeat for stale-worker recovery based on liveness.
--
-- A batch run may legitimately take longer than the recovery window (e.g. many
-- cases / slow LLM). previoUsly, stale judgement used started_at, so a healthy
-- run still in progress after N minutes was wrongly failed. We add an
-- heartbeat_at column refreshed after every processed case. The recovery sweep
-- now compares against heartbeat_at (falling back to started_at when no case
-- has been processed yet) so only truly silent runs are reclaimed.

ALTER TABLE `prompt_test_set_run`
    ADD COLUMN `heartbeat_at` DATETIME DEFAULT NULL
        COMMENT 'last liveness heartbeat; refreshed after each processed case';

-- Recovery sweep filters on status + heartbeat_at (with started_at fallback),
-- so index the leading status column together with heartbeat_at to keep the
-- scan fast as run history grows.
CREATE INDEX idx_ptsr_status_heartbeat ON prompt_test_set_run (status, heartbeat_at);