-- V63: 招投标垂直化 —— 招标评分办法
-- points_json: JSON 数组 [{name, max_score, weight, scoring_criteria, evidence}]
CREATE TABLE bid_scoring_method (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id          BIGINT NOT NULL DEFAULT 1 COMMENT '租户',
    project_id         BIGINT NOT NULL COMMENT 'FK → bid_project.id',
    method_type        VARCHAR(32) NOT NULL COMMENT 'comprehensive(综合评分法)|lowest_price(最低价法)',
    points_json        TEXT COMMENT '评分点 JSON',
    total_score        DECIMAL(8,2) DEFAULT NULL COMMENT '满分',
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted            TINYINT NOT NULL DEFAULT 0,
    INDEX idx_bid_scoring_project (project_id),
    INDEX idx_bid_scoring_tenant (tenant_id)
) COMMENT='招标评分办法';
