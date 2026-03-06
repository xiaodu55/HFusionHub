-- =====================================================
-- HFusionHub V10.1 — 修正历史非法终态 (completed → succeeded)
-- =====================================================
-- 背景: V10 上线初期 Java 直接透传 Python 的 status: "completed"，
-- 但合约终态只允许 succeeded / failed / cancelled / timed_out。
-- 本迁移一次性将已存在的 completed 记录修正为 succeeded。

UPDATE `agent_task` SET `status` = 'succeeded' WHERE `status` = 'completed';
UPDATE `agent_run`  SET `status` = 'succeeded' WHERE `status` = 'completed';
UPDATE `agent_task` SET `status` = 'timed_out' WHERE `status` = 'timeout';
UPDATE `agent_run`  SET `status` = 'timed_out' WHERE `status` = 'timeout';
UPDATE `agent_task` SET `status` = 'failed'    WHERE `status` = 'tool_error';
UPDATE `agent_run`  SET `status` = 'failed'    WHERE `status` = 'tool_error';
