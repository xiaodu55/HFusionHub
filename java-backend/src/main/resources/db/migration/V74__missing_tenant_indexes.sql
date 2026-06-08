-- ============================================================
-- V74: 补齐 tenant_id 前导索引（第十五轮 P1，R15-12）
--
-- 背景：V32 为大部分租户表加了 idx_*_tenant，但漏了 8 张（见下）；
-- V24/V37/V41/V47/V52/V54/V55/V56 建表时也未建租户索引。所有租户行
-- 拦截器查询都以 tenant_id = ? 过滤，缺索引意味着全表扫描。
-- 本迁移按 V61-V68 招投标表的做法统一补齐（索引名 idx_<缩写>_tenant）。
--
-- 注意：均加普通非唯一索引，不改变约束语义；H2 测试 schema（Flyway
-- 关闭）不受影响。app_api_key / kb_share / rag_intent_node / user_model_config
-- 已有 tenant_id 前导索引（V52/V56/V41/V47），无需处理。
-- feature_flag_rule 无 tenant_id 列（其规则作用域存于 scope_value，见 V24），
-- 不在本迁移范围内。
-- ============================================================

-- V32 遗漏
ALTER TABLE agent_alert_rule        ADD INDEX idx_aar_tenant (tenant_id);
ALTER TABLE agent_alert_event       ADD INDEX idx_aae_tenant (tenant_id);
ALTER TABLE agent_evaluation_dataset ADD INDEX idx_aed_tenant (tenant_id);
ALTER TABLE prompt_test_set         ADD INDEX idx_pts_tenant (tenant_id);
ALTER TABLE prompt_test_set_run     ADD INDEX idx_ptsr_tenant (tenant_id);

-- 开放 API / 审计 / 笔记（V52/V54/V55）
ALTER TABLE app_call_log            ADD INDEX idx_acl_tenant (tenant_id);
ALTER TABLE audit_log               ADD INDEX idx_audit_tenant (tenant_id);
ALTER TABLE note                    ADD INDEX idx_note_tenant (tenant_id);

-- Webhook 订阅（V37）
ALTER TABLE webhook_subscription    ADD INDEX idx_whs_tenant (tenant_id);
