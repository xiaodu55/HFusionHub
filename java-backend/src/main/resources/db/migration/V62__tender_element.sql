-- V62: 招投标垂直化 —— 招标文件结构化要素
-- 由 Python 解读工作流产出，Java 落库；(project_id, element_key) 唯一。
-- element_key 枚举：tender_number|budget|qualification_requirements|scoring_method|deadline|bid_bond|disqualification_clauses|substantive_response_clauses|bid_currency|contact
CREATE TABLE tender_element (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id          BIGINT NOT NULL DEFAULT 1 COMMENT '租户',
    project_id         BIGINT NOT NULL COMMENT 'FK → bid_project.id',
    element_key        VARCHAR(64) NOT NULL COMMENT '要素键',
    element_value      TEXT COMMENT '要素内容（JSON 或文本）',
    evidence_chunk_ids TEXT COMMENT '证据 chunk id 列表（JSON 数组，用于追溯）',
    confidence         DECIMAL(5,4) DEFAULT NULL COMMENT '置信度 0-1',
    source_clause      TEXT DEFAULT NULL COMMENT '来源条款原文',
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted            TINYINT NOT NULL DEFAULT 0,
    INDEX idx_tender_element_project (project_id),
    INDEX idx_tender_element_tenant (tenant_id),
    UNIQUE KEY uk_tender_element (project_id, element_key)
) COMMENT='招标文件结构化要素';
