-- V59: 解锁多 Agent 协作（agent.multi_agent.enabled 默认开启）。
-- BoundedMultiAgentWorkflow（检索/分析/校验 角色并发协作 + 确定性证据校验器）已有
-- 回归测试覆盖（test_multi_agent_workflow.py、流式证据门控），按用户要求解除冻结，
-- 将 agent.multi_agent.enabled 默认置为 TRUE。
-- 实际生效依赖 agent.enabled（复杂任务模式）同时开启；仍可在前端「能力开关」页按需关闭。
UPDATE feature_flag SET enabled = TRUE WHERE flag_key = 'agent.multi_agent.enabled';
