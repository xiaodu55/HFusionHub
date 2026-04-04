-- HFusionHub V34 — Tenant audit log for platform-admin cross-tenant operations
-- Records "act on behalf of" actions: which platform admin, from which tenant,
-- to which target tenant, and the action performed. NOT tenant-scoped reads
-- (no tenant_id filter); kept as a global accountability trail.
CREATE TABLE IF NOT EXISTS tenant_audit_log (
    id            BIGINT      NOT NULL AUTO_INCREMENT,
    operator_id   BIGINT      NOT NULL COMMENT '平台管理员 user id',
    from_tenant   BIGINT      NOT NULL COMMENT '管理员自身租户',
    to_tenant     BIGINT      NOT NULL COMMENT '代操作目标租户',
    action        VARCHAR(500) NOT NULL COMMENT 'HTTP 方法 + 路径',
    created_at    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_tal_to_tenant (to_tenant),
    INDEX idx_tal_operator (operator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户跨租户代操作审计';