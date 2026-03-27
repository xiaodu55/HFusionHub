-- Prompt Test Set Run — per-execution token for stale-worker isolation.
--
-- Each execution (initial run or a retry) gets a fresh, non-reusable
-- execution_token. Workers guard every progress/result/terminal write with
-- this token as an optimistic lock. Retry regenerates the token, so a stale
-- worker that survived cancel no longer matches any write guard and aborts
-- before polluting the new attempt. Case results are tagged with the token
-- that produced them so reads only surface the current attempt's results.

ALTER TABLE `prompt_test_set_run`
    ADD COLUMN `execution_token` VARCHAR(64) DEFAULT NULL
        COMMENT 'unique per execution; regenerated on each retry';

ALTER TABLE `prompt_test_case_result`
    ADD COLUMN `execution_token` VARCHAR(64) DEFAULT NULL
        COMMENT 'execution token of the run attempt that produced this result';

CREATE INDEX idx_ptcr_run_token ON prompt_test_case_result (run_id, execution_token);
