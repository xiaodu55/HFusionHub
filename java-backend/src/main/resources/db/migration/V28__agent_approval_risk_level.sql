-- HFusionHub V28 — Agent approval risk level for the approval UI / audit trail.
-- Captured from the Python tool spec (read_only | read_write | external) when an
-- approval is created, so the approver can see the tool's risk before deciding.
ALTER TABLE `agent_approval`
    ADD COLUMN `risk_level` VARCHAR(32) DEFAULT 'read_only' COMMENT '工具风险等级: read_only|read_write|external' AFTER `tool_name`;