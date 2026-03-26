-- Prompt Test Set Async Run — queueing, real-time progress, cancellation and retry.
--
-- The batch run becomes an async task:
--   pending -> running -> succeeded | failed | cancelled
-- progress_count tracks completed cases for live progress; attempt_number supports
-- run-level retry; stale running runs are reclaimed by the recovery sweep.

ALTER TABLE `prompt_test_set_run`
    ADD COLUMN `status` VARCHAR(20) NOT NULL DEFAULT 'succeeded'
        COMMENT 'pending|running|succeeded|failed|cancelled',
    ADD COLUMN `attempt_number` INT NOT NULL DEFAULT 1 COMMENT 'run retry attempt number',
    ADD COLUMN `progress_count` INT NOT NULL DEFAULT 0 COMMENT 'cases completed so far',
    ADD COLUMN `error_message` VARCHAR(2000) DEFAULT NULL COMMENT 'terminal failure reason',
    ADD COLUMN `scheduled_at` DATETIME DEFAULT NULL COMMENT 'when the run became queued',
    ADD COLUMN `started_at` DATETIME DEFAULT NULL COMMENT 'when the worker claimed the run',
    ADD COLUMN `completed_at` DATETIME DEFAULT NULL COMMENT 'when the run reached a terminal state';

CREATE INDEX idx_ptsr_status_scheduled ON prompt_test_set_run (status, scheduled_at);
