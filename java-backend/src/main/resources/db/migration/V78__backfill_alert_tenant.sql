-- V78: 回填 V32 遗留的 NULL 租户行（docs/REPAIR_ROADMAP.md Low 批）
-- V32 对 agent_alert_rule/event 只回填了 user_id 非空的行（WHERE user_id IS NOT NULL），
-- 无 user 的系统级行 tenant_id 保持 NULL —— 租户拦截器注入 tenant_id 条件后这些行
-- 永远查不到（不可见即不可管理，告警配置形同虚设）。
-- 系统级行归默认租户 1（平台初始租户，V1 建立）。

UPDATE `agent_alert_rule`  SET `tenant_id` = 1 WHERE `tenant_id` IS NULL;
UPDATE `agent_alert_event` SET `tenant_id` = 1 WHERE `tenant_id` IS NULL;
