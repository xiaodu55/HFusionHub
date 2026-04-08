-- HFusionHub V37 — Webhook 订阅与投递
-- webhook_subscription  订阅配置（软删除），webhook_delivery 投递记录（追加式）。
-- 订阅带 tenant_id 列，由租户行拦截器自动隔离；投递记录不落租户列，
-- 通过 subscription_id 回溯归属（已在 MybatisPlusConfig.TENANT_IGNORE_TABLES 中登记）。
CREATE TABLE IF NOT EXISTS webhook_subscription (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT,
    name VARCHAR(200) NOT NULL,
    url VARCHAR(1000) NOT NULL,
    secret VARCHAR(200),
    events TEXT NOT NULL COMMENT 'JSON array of event types',
    is_active TINYINT NOT NULL DEFAULT 1,
    last_triggered_at DATETIME,
    failure_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS webhook_delivery (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    subscription_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    response_status INT,
    response_body TEXT,
    duration_ms INT,
    success TINYINT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_wd_subscription (subscription_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
