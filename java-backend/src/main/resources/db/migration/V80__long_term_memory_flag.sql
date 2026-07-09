-- V80: 长期记忆接线（Batch 1）— 注册 memory.long_term.enabled 特性开关。
-- 闭环组成：Python MemoryConsolidator（LLM 记忆抽取，每 N 轮 + 会话删除回调）
--   → Java /internal/memory/entries 落 memory_entry 表
--   → Agent 组装上下文前经 /internal/memory/relevant 拉取注入。
-- 默认关闭（enabled = FALSE）；可在前端「能力开关」页按租户/用户灰度打开。
INSERT IGNORE INTO feature_flag (flag_key, flag_type, description, enabled) VALUES
('memory.long_term.enabled', 'boolean',
 '长期记忆：会话边界自动抽取记忆并在后续对话注入（含会话删除回调 consolidate）',
 FALSE);
