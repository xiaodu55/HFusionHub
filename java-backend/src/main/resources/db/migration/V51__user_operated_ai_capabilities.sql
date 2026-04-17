-- Runtime AI capabilities managed from the admin UI.
INSERT IGNORE INTO feature_flag (flag_key, flag_type, description, enabled) VALUES
('rag.hybrid.enabled', 'boolean', '同时使用向量检索和关键词检索', TRUE);

UPDATE feature_flag SET description = '关联文档中的实体关系，补充复杂知识检索' WHERE flag_key = 'rag.graph.enabled';
UPDATE feature_flag SET description = '对初步检索结果再次排序，提高引用准确度' WHERE flag_key = 'rag.reranker.enabled';
UPDATE feature_flag SET description = '为复杂 Agent 任务增加超时、重试和执行边界' WHERE flag_key = 'agent.enabled';
UPDATE feature_flag SET description = '让分析与校验 Agent 协作处理复杂问题' WHERE flag_key = 'agent.multi_agent.enabled';
UPDATE feature_flag SET description = '允许 Agent 搜索互联网中的最新信息' WHERE flag_key = 'agent.web_search.enabled';
UPDATE feature_flag SET description = '允许 Agent 发起写入操作，执行前仍受人工确认保护' WHERE flag_key = 'agent.write_tools.enabled';
UPDATE feature_flag SET description = '写入类操作执行前必须由用户确认' WHERE flag_key = 'approval.required_for_write';
