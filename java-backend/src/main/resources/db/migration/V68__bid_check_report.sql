-- V68: 招投标垂直化 —— 废标风险自检报告（自检工作流产出）
-- severity: critical|warning|info（critical 级必须人工确认才能放行）
-- category: disqualification(废标条款对照)|substantive(实质性响应)|format(格式)|bond(保证金)|deadline(工期/时间)
-- status: open|confirmed|fixed
CREATE TABLE bid_check_report (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id     BIGINT NOT NULL DEFAULT 1 COMMENT '租户',
    project_id    BIGINT NOT NULL COMMENT 'FK → bid_project.id',
    section_key   VARCHAR(32) DEFAULT NULL COMMENT '定位到分节（可空=项目级）',
    severity      VARCHAR(16) NOT NULL DEFAULT 'warning' COMMENT 'critical|warning|info',
    category      VARCHAR(32) NOT NULL COMMENT '检查类别',
    finding       TEXT NOT NULL COMMENT '问题描述',
    evidence      JSON DEFAULT NULL COMMENT '证据引用（chunk_id 列表/原文）',
    suggested_fix TEXT DEFAULT NULL COMMENT '修复建议',
    status        VARCHAR(16) NOT NULL DEFAULT 'open' COMMENT 'open|confirmed|fixed',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted       TINYINT NOT NULL DEFAULT 0,
    INDEX idx_bid_check_project (project_id),
    INDEX idx_bid_check_tenant (tenant_id)
) COMMENT='废标风险自检报告';
