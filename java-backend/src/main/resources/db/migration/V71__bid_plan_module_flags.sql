-- ============================================================
-- V71: 投标套餐模块开关（P2-2）
--
-- 四个平台级 FeatureFlag 作为"运营开关"，叠加在套餐授权（tenant_plan_binding.module_flags）
-- 之上：套餐授权是"资格底线"，FeatureFlag 提供全局下架 / 环境灰度 / 租户覆盖能力。
--   module_enabled = 套餐已授权  AND  feature_flag 未关闭（全局默认开）
--
-- feature_flag 已在 TENANT_IGNORE_TABLES，无需 tenant_id。
-- ============================================================

INSERT INTO feature_flag (flag_key, flag_type, description, enabled) VALUES
    ('bid.module.draft',   'boolean', '投标撰写模块开关（P2-2 套餐模块 draft）', TRUE),
    ('bid.module.check',   'boolean', '废标自检模块开关（P2-2 套餐模块 check）', TRUE),
    ('bid.module.docx',    'boolean', 'DOCX 导出模块开关（P2-2 套餐模块 docx）', TRUE),
    ('bid.module.openapi', 'boolean', '投标开放 API 模块开关（P2-2 套餐模块 openapi）', TRUE);
