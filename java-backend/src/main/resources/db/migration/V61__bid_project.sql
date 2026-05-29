-- V61: 招投标垂直化 —— 投标项目主表
-- 一个 bid_project 对应一次投标任务，关联「招标文件库」（knowledge_base.category=tender）。
-- status 状态机：interpreting → requirements → drafting → checking → submitted/archived
CREATE TABLE bid_project (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id          BIGINT NOT NULL DEFAULT 1 COMMENT '租户',
    knowledge_base_id  BIGINT NOT NULL COMMENT '招标文件所在知识库 FK → knowledge_base.id',
    tender_number      VARCHAR(128) DEFAULT NULL COMMENT '招标编号',
    title              VARCHAR(255) NOT NULL COMMENT '项目名称',
    budget             DECIMAL(18,2) DEFAULT NULL COMMENT '预算金额',
    deadline           VARCHAR(64) DEFAULT NULL COMMENT '工期/交货期',
    bid_bond           VARCHAR(64) DEFAULT NULL COMMENT '投标保证金要求',
    opening_date       DATETIME DEFAULT NULL COMMENT '开标时间',
    status             VARCHAR(32) NOT NULL DEFAULT 'interpreting' COMMENT 'interpreting|requirements|drafting|checking|submitted|archived',
    created_by         BIGINT DEFAULT NULL COMMENT '创建人 sys_user.id',
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted            TINYINT NOT NULL DEFAULT 0,
    INDEX idx_bid_project_tenant (tenant_id),
    INDEX idx_bid_project_kb (knowledge_base_id)
) COMMENT='投标项目';
