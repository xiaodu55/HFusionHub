-- ============================================================
-- V72: 行业方案包（P2-7 商业化）—— 平台套餐 + 平台级标书模板
--
-- 1) 两个行业方案包进 bid_subscription（platform catalog，tenant_id NULL）
--    - 按 tenant_plan_binding 授权售卖，不改 tenant.plan_tier
--    - industry 语义由 plan_code 编码：industry_construction / industry_it
-- 2) 平台级 bid_template（tenant_id NULL，行业方案包基础），租户可见（P2-7 已加入
--    TENANT_IGNORE_TABLES，服务层过滤平台+自有）
-- ============================================================

INSERT INTO bid_subscription
    (plan_code, plan_name, plan_type, price_cents, max_projects, max_seats, char_quota, module_flags)
VALUES
    ('industry_construction', '工程施工行业方案包', 'industry', 19900, 50, 20, 5000000,
     JSON_OBJECT('draft', 1, 'check', 1, 'docx', 1, 'openapi', 1)),
    ('industry_it',          'IT 集成行业方案包',   'industry', 19900, 50, 20, 5000000,
     JSON_OBJECT('draft', 1, 'check', 1, 'docx', 1, 'openapi', 1));

INSERT INTO bid_template
    (tenant_id, name, description, industry, section_defs, is_active)
VALUES
    (NULL, '工程施工标书模板',
     '工程施工行业方案包预置：商务标/技术标/施工组织设计/资质标等分节',
     'construction',
     JSON_ARRAY(
         JSON_OBJECT('key', 'commercial', 'title', '商务标'),
         JSON_OBJECT('key', 'technical', 'title', '技术标'),
         JSON_OBJECT('key', 'org', 'title', '施工组织设计'),
         JSON_OBJECT('key', 'qualification', 'title', '资质标')),
     1),
    (NULL, 'IT 集成标书模板',
     'IT 集成行业方案包预置：商务标/技术方案/实施与售后/资质标等分节',
     'it',
     JSON_ARRAY(
         JSON_OBJECT('key', 'commercial', 'title', '商务标'),
         JSON_OBJECT('key', 'solution', 'title', '技术方案'),
         JSON_OBJECT('key', 'implementation', 'title', '实施与售后'),
         JSON_OBJECT('key', 'qualification', 'title', '资质标')),
     1);
