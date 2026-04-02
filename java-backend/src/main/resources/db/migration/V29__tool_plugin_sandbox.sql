-- HFusionHub V29 — Tool Plugin Sandbox & Supply Chain Governance
-- Plugin registry, audit trail, and dependency lock tables.

-- =====================================================
-- Plugin registry
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin (
    id                     BIGINT       NOT NULL AUTO_INCREMENT,
    plugin_id              VARCHAR(36)  NOT NULL COMMENT 'UUID',
    name                   VARCHAR(100) NOT NULL COMMENT '机器名: github_connector',
    display_name           VARCHAR(200) DEFAULT NULL COMMENT '显示名称',
    description            TEXT         DEFAULT NULL,
    version                VARCHAR(32)  NOT NULL COMMENT '语义化版本 semver',
    author                 VARCHAR(100) DEFAULT NULL,
    author_email           VARCHAR(200) DEFAULT NULL,
    license                VARCHAR(64)  DEFAULT NULL,
    min_hfusionhub_version VARCHAR(32)  DEFAULT NULL,
    max_hfusionhub_version VARCHAR(32)  DEFAULT NULL,
    icon_url               VARCHAR(500) DEFAULT NULL,
    source                 VARCHAR(32)  NOT NULL DEFAULT 'local' COMMENT 'local|git|wheel',
    status                 VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active|disabled|failed|pending',
    manifest_hash          VARCHAR(64)  DEFAULT NULL COMMENT 'SHA-256 of manifest JSON',
    artifact_path          VARCHAR(500) DEFAULT NULL COMMENT 'Path to wheel',
    artifact_hash          VARCHAR(64)  DEFAULT NULL COMMENT 'SHA-256 of wheel file',
    sandbox_config         TEXT         DEFAULT NULL COMMENT 'JSON sandbox constraints',
    permissions            TEXT         DEFAULT NULL COMMENT 'JSON permission list',
    enabled                TINYINT      NOT NULL DEFAULT 1,
    installed_by           BIGINT       DEFAULT NULL,
    installed_at           TIMESTAMP    NULL DEFAULT NULL,
    created_at             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted                TINYINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_plugin_id (plugin_id),
    FOREIGN KEY (installed_by) REFERENCES sys_user (id) ON DELETE SET NULL
);

CREATE INDEX idx_plugin_name ON plugin (name);
CREATE INDEX idx_plugin_status ON plugin (status);

-- =====================================================
-- Plugin audit log
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_audit_log (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    event_id    VARCHAR(36)  DEFAULT NULL COMMENT 'UUID idempotency key from Python AI',
    plugin_id   BIGINT       NOT NULL COMMENT 'FK to plugin.id',
    plugin_name VARCHAR(100) DEFAULT NULL,
    action      VARCHAR(32)  NOT NULL COMMENT 'install|enable|disable|update|uninstall|rollback',
    operator_id BIGINT       DEFAULT NULL,
    old_value   TEXT         DEFAULT NULL,
    new_value   TEXT         DEFAULT NULL,
    reason      VARCHAR(500) DEFAULT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_audit_event_id (event_id),
    FOREIGN KEY (plugin_id) REFERENCES plugin (id) ON DELETE CASCADE
);

CREATE INDEX idx_plugin_audit_plugin ON plugin_audit_log (plugin_id);
CREATE INDEX idx_plugin_audit_time ON plugin_audit_log (created_at);

-- =====================================================
-- Plugin dependency lock
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_dependency (
    id                BIGINT       NOT NULL AUTO_INCREMENT,
    plugin_id         BIGINT       NOT NULL COMMENT 'FK to plugin.id',
    dependency_name   VARCHAR(100) NOT NULL,
    dependency_version VARCHAR(32) DEFAULT NULL COMMENT 'semver range',
    optional          TINYINT      NOT NULL DEFAULT 0,
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_plugin_dep (plugin_id, dependency_name),
    FOREIGN KEY (plugin_id) REFERENCES plugin (id) ON DELETE CASCADE
);

CREATE INDEX idx_plugin_dep_plugin ON plugin_dependency (plugin_id);
