-- C1: 操作审计日志（敏感操作）
CREATE TABLE audit_log (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    operator_id   BIGINT NOT NULL COMMENT '操作人（sys_user.id）',
    tenant_id     BIGINT NOT NULL DEFAULT 1,
    action        VARCHAR(50) NOT NULL COMMENT '如 app.publish, api_key.create, kb.share',
    target_type   VARCHAR(50) NOT NULL COMMENT '如 app, app_api_key, kb_share, system_notice',
    target_id     VARCHAR(64) DEFAULT NULL,
    detail        VARCHAR(500) DEFAULT NULL COMMENT '摘要（不含敏感数据）',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_operator (operator_id, created_at),
    INDEX idx_audit_target (target_type, target_id)
) COMMENT='操作审计日志';
