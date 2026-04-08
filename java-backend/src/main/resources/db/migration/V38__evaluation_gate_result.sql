-- HFusionHub V38 — 评测回归门禁结果
-- 每次执行评测门禁（checkGate）持久化一条结果，供门禁历史查询与趋势分析。
-- 无 tenant_id 列：访问受数据集归属校验保护（与 agent_evaluation_run 同模式），
-- 已在 MybatisPlusConfig.TENANT_IGNORE_TABLES 中登记。
CREATE TABLE IF NOT EXISTS evaluation_gate_result (
    id BIGINT NOT NULL AUTO_INCREMENT,
    dataset_id BIGINT NOT NULL,
    run_id BIGINT NOT NULL,
    run_uuid VARCHAR(64) NOT NULL,
    passed TINYINT NOT NULL DEFAULT 0,
    accuracy DECIMAL(6,4),
    latency_p95 INT,
    token_cost DECIMAL(12,6),
    baseline_run_uuid VARCHAR(64),
    baseline_token_cost DECIMAL(12,6),
    criteria_json TEXT COMMENT '门禁判定明细 JSON',
    details TEXT COMMENT '补充说明 JSON',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_egr_dataset (dataset_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='评测回归门禁结果';
