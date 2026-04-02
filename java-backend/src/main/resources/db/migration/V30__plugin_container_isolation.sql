-- HFusionHub V30 — Plugin Container Isolation, Canary & Health
-- Adds canary release, health check, metrics, and version tracking columns.

-- =====================================================
-- Plugin table additions
-- =====================================================
ALTER TABLE plugin ADD COLUMN canary_weight DECIMAL(3,2) DEFAULT 0.00 COMMENT 'Canary traffic weight (0.00-1.00)';
ALTER TABLE plugin ADD COLUMN circuit_open_until DATETIME DEFAULT NULL COMMENT 'Circuit breaker open until timestamp';
ALTER TABLE plugin ADD COLUMN previous_version VARCHAR(32) DEFAULT NULL COMMENT 'Previous version for rollback';
ALTER TABLE plugin ADD COLUMN health_status VARCHAR(16) DEFAULT 'unknown' COMMENT 'healthy|unhealthy|unknown';
ALTER TABLE plugin ADD COLUMN last_health_check DATETIME DEFAULT NULL COMMENT 'Last health probe timestamp';
ALTER TABLE plugin ADD COLUMN sbom_json MEDIUMTEXT DEFAULT NULL COMMENT 'CycloneDX SBOM JSON';
ALTER TABLE plugin ADD COLUMN vulnerability_status VARCHAR(16) DEFAULT 'pending' COMMENT 'clean|vulnerable|pending|error';
ALTER TABLE plugin ADD COLUMN last_scan_at DATETIME DEFAULT NULL COMMENT 'Last vulnerability scan timestamp';
ALTER TABLE plugin ADD COLUMN container_image VARCHAR(256) DEFAULT NULL COMMENT 'Docker image tag for container execution';

-- =====================================================
-- Plugin execution metrics (aggregate, time-series)
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_execution_metric (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    plugin_id   BIGINT       NOT NULL COMMENT 'FK to plugin.id',
    metric_name VARCHAR(128) NOT NULL COMMENT 'Metric identifier',
    metric_value DOUBLE      NOT NULL COMMENT 'Metric value',
    labels      TEXT         DEFAULT NULL COMMENT 'JSON key-value labels',
    recorded_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_plugin_metric (plugin_id, metric_name, recorded_at),
    FOREIGN KEY (plugin_id) REFERENCES plugin (id) ON DELETE CASCADE
);

-- =====================================================
-- Plugin health check log
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_health_log (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    plugin_id   BIGINT       NOT NULL COMMENT 'FK to plugin.id',
    check_type  VARCHAR(32)  NOT NULL COMMENT 'liveness|readiness',
    status      VARCHAR(16)  NOT NULL COMMENT 'healthy|unhealthy',
    details     TEXT         DEFAULT NULL COMMENT 'JSON check details',
    duration_ms FLOAT        DEFAULT NULL COMMENT 'Check duration in milliseconds',
    checked_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_plugin_health (plugin_id, checked_at),
    FOREIGN KEY (plugin_id) REFERENCES plugin (id) ON DELETE CASCADE
);

-- =====================================================
-- Plugin version history (for rollback)
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_version_history (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    plugin_id    BIGINT       NOT NULL COMMENT 'FK to plugin.id',
    version      VARCHAR(32)  NOT NULL,
    artifact_key VARCHAR(500) DEFAULT NULL COMMENT 'MinIO object key',
    artifact_hash VARCHAR(64) DEFAULT NULL,
    manifest_json TEXT        DEFAULT NULL COMMENT 'Full manifest at this version',
    is_canary    TINYINT      NOT NULL DEFAULT 0,
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_plugin_version (plugin_id, version),
    FOREIGN KEY (plugin_id) REFERENCES plugin (id) ON DELETE CASCADE
);
