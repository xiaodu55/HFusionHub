-- V70: 招投标垂直化 —— 租户套餐绑定（P2 商业化）
-- 多套餐支持：租户可同时绑定基础档位（tier）+ 多个行业方案包（industry），按授权售卖。
-- 本表为租户私有（tenant_id NOT NULL），由租户行拦截器自动隔离。
CREATE TABLE tenant_plan_binding (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id       BIGINT NOT NULL COMMENT '租户 ID（租户隔离）',
    subscription_id BIGINT NOT NULL COMMENT 'FK bid_subscription.id',
    start_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '生效时间',
    end_at          DATETIME DEFAULT NULL COMMENT '到期时间；NULL=长期有效',
    status          VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT 'active|expired|canceled',
    created_by      BIGINT DEFAULT NULL COMMENT '操作人',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_binding_tenant_plan (tenant_id, subscription_id),
    INDEX idx_binding_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户套餐绑定';
