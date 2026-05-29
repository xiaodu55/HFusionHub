-- V67: 招投标垂直化 —— 标书模板
-- tenant_id 可空 = 平台级模板（P2 行业方案包的基础）；非空 = 租户私有模板
-- section_defs: JSON 数组 [{"key":"commercial","title":"商务标"},...] 定义分节结构
CREATE TABLE bid_template (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id    BIGINT DEFAULT NULL COMMENT '租户；NULL=平台级模板',
    name         VARCHAR(128) NOT NULL COMMENT '模板名称',
    description  VARCHAR(512) DEFAULT NULL COMMENT '模板说明',
    industry     VARCHAR(64) DEFAULT NULL COMMENT '行业分类（工程施工/IT集成等）',
    section_defs JSON NOT NULL COMMENT '分节定义 JSON 数组',
    is_active    TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用',
    created_by   BIGINT DEFAULT NULL COMMENT '创建人',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted      TINYINT NOT NULL DEFAULT 0,
    INDEX idx_bid_template_tenant (tenant_id)
) COMMENT='标书模板';
