-- V66: 招投标垂直化 —— 标书分节草稿（撰写工作流产出）
-- section_key: commercial(商务)|technical(技术)|qualification(资质)|format(格式)
-- status: drafting|approved|rejected（P1-2 每节人工审批流转）
-- version: 分节重写递增，保留可回滚版本记录
CREATE TABLE bid_draft (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id     BIGINT NOT NULL DEFAULT 1 COMMENT '租户',
    project_id    BIGINT NOT NULL COMMENT 'FK → bid_project.id',
    section_key   VARCHAR(32) NOT NULL COMMENT '分节标识 commercial|technical|qualification|format',
    section_title VARCHAR(128) NOT NULL COMMENT '分节标题',
    content       LONGTEXT COMMENT '分节正文（长文）',
    status        VARCHAR(32) NOT NULL DEFAULT 'drafting' COMMENT 'drafting|approved|rejected',
    version       INT NOT NULL DEFAULT 1 COMMENT '分节版本号',
    approved_by   BIGINT DEFAULT NULL COMMENT '审批人',
    created_by    BIGINT NOT NULL COMMENT '创建人',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted       TINYINT NOT NULL DEFAULT 0,
    INDEX idx_bid_draft_project (project_id),
    INDEX idx_bid_draft_tenant (tenant_id)
) COMMENT='标书分节草稿';
