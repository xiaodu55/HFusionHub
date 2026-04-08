-- V36: Cost tracking — model usage records for cost governance
CREATE TABLE IF NOT EXISTS model_usage_record (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT,
    conversation_id BIGINT,
    agent_task_id BIGINT,
    model VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    latency_ms INT NOT NULL DEFAULT 0,
    request_type VARCHAR(50) NOT NULL COMMENT 'chat|embedding|agent|evaluation',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_mur_user (user_id, created_at),
    INDEX idx_mur_tenant (tenant_id, created_at),
    INDEX idx_mur_model (model, created_at),
    INDEX idx_mur_request_type (request_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
