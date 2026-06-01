-- V69: 招投标垂直化 —— 订阅套餐目录（P2 商业化）
-- tenant_id 可空 = 平台内置套餐（free/pro/enterprise + 行业方案包）；非空 = 租户自定义套餐
-- module_flags: JSON {"draft":true,"check":true,"docx":false,"openapi":false}
-- 供 P2-2 工作流模块开关使用（与 QuotaProperties 的 free/pro/enterprise 默认值对齐）。
-- 本表为平台目录，加入 MybatisPlusConfig.TENANT_IGNORE_TABLES（租户查询可见全目录）。
CREATE TABLE bid_subscription (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id    BIGINT DEFAULT NULL COMMENT '租户；NULL=平台内置套餐',
    plan_code    VARCHAR(32) NOT NULL COMMENT '套餐代码 free|pro|enterprise|industry_construction|industry_it',
    plan_name    VARCHAR(64) NOT NULL COMMENT '套餐名称',
    plan_type    VARCHAR(16) NOT NULL DEFAULT 'tier' COMMENT 'tier=基础档位|industry=行业方案包',
    price_cents  BIGINT NOT NULL DEFAULT 0 COMMENT '月度价格（分）',
    max_projects INT NOT NULL DEFAULT 5 COMMENT '最大投标项目数',
    max_seats    INT NOT NULL DEFAULT 5 COMMENT '最大坐席数（tenant_member 数）',
    char_quota   BIGINT NOT NULL DEFAULT 100000 COMMENT '标书撰写月度字符额度',
    module_flags JSON NOT NULL COMMENT '模块开关 JSON',
    status       VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT 'active|archived',
    created_by   BIGINT DEFAULT NULL COMMENT '创建人',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted      TINYINT NOT NULL DEFAULT 0,
    UNIQUE KEY uk_subscription_code (plan_code),
    INDEX idx_subscription_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订阅套餐目录';

-- 平台内置套餐（与 QuotaProperties free/pro/enterprise 档位默认值一致）
INSERT INTO bid_subscription
    (plan_code, plan_name, plan_type, price_cents, max_projects, max_seats, char_quota, module_flags)
VALUES
    ('free', '免费版',   'tier', 0,     3,   3,  100000,  JSON_OBJECT('draft', 1, 'check', 1, 'docx', 0, 'openapi', 0)),
    ('pro',  '专业版',   'tier', 9900,  20,  10, 1000000, JSON_OBJECT('draft', 1, 'check', 1, 'docx', 0, 'openapi', 1)),
    ('enterprise', '企业版', 'tier', 39900, 100, 50, 10000000, JSON_OBJECT('draft', 1, 'check', 1, 'docx', 1, 'openapi', 1));
