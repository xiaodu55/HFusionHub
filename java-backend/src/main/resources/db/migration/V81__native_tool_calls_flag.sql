-- V81: 原生 function calling（Batch 2）— 注册 agent.native_tool_calls.enabled 特性开关。
-- 开启后 ReAct Agent 优先使用 provider 原生 tool-calls（DeepSeek / OpenAI 兼容端点 /
-- Ollama ≥0.4 /api/chat），provider 不支持或调用失败时自动降级文本 Thought/Action 协议；
-- 步数上限由 RAG_AGENT_MAX_STEPS 配置（默认 12）。默认关闭。
INSERT IGNORE INTO feature_flag (flag_key, flag_type, description, enabled) VALUES
('agent.native_tool_calls.enabled', 'boolean',
 '原生 function calling：ReAct 优先 provider 原生 tool-calls（失败自动降级文本 ReAct）',
 FALSE);
