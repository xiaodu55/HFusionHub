-- V64: 招投标垂直化 —— 投标需求清单（解读产出）
-- category: qualification(资质)|performance(业绩)|technical(技术)|commercial(商务)|format(格式)|disqualification_risk(废标风险)
-- satisfied_status: pending|drafting|checked|manual_review（低置信要素强制人工确认）
CREATE TABLE bid_requirement (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id          BIGINT NOT NULL DEFAULT 1 COMMENT '租户',
    project_id         BIGINT NOT NULL COMMENT 'FK → bid_project.id',
    category           VARCHAR(32) NOT NULL COMMENT '需求类别',
    requirement        TEXT NOT NULL COMMENT '需求描述',
    source_clause      TEXT DEFAULT NULL COMMENT '来源条款原文',
    satisfied_status   VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT 'pending|drafting|checked|manual_review',
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted            TINYINT NOT NULL DEFAULT 0,
    INDEX idx_bid_requirement_project (project_id),
    INDEX idx_bid_requirement_tenant (tenant_id)
) COMMENT='投标需求清单';
