-- Persist the exact approved tool parameters so a resume cannot substitute a summary.
ALTER TABLE `agent_approval`
    ADD COLUMN `tool_input` TEXT NULL COMMENT '原始工具参数 JSON（仅用于哈希校验和精确恢复）' AFTER `tool_input_hash`;
