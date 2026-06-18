-- V76: 补齐 tenant_plan_binding 缺失的逻辑删除列
--
-- TenantPlanBinding 继承 BaseEntity（含全局逻辑删除字段 deleted，
-- application.yml logic-delete-field），MyBatis-Plus 会为该表所有查询
-- 自动追加 deleted 字段；V70 建表时遗漏该列，导致 /bid/plan/current
-- 等接口 BadSqlGrammarException（Unknown column 'deleted'）500。
ALTER TABLE tenant_plan_binding
    ADD COLUMN deleted TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除（BaseEntity 全局字段）';
