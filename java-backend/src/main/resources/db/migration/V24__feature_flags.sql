-- Feature Flag system: 5-layer override (global → tenant → user → KB → environment)
-- Tables: feature_flag, feature_flag_rule, feature_flag_audit_log

CREATE TABLE feature_flag (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    flag_key      VARCHAR(100) NOT NULL UNIQUE COMMENT 'e.g. agent.enabled, rag.graph.enabled',
    flag_type     ENUM('boolean','percentage','whitelist','blacklist') NOT NULL DEFAULT 'boolean',
    description   VARCHAR(500) DEFAULT NULL,
    enabled       BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Global on/off',
    percentage    INT          DEFAULT NULL COMMENT '0-100, for percentage rollout',
    whitelist     TEXT         DEFAULT NULL COMMENT 'JSON array of IDs for whitelist',
    blacklist     TEXT         DEFAULT NULL COMMENT 'JSON array of IDs for blacklist',
    start_time    DATETIME     DEFAULT NULL COMMENT 'Effective start (NULL = always)',
    end_time      DATETIME     DEFAULT NULL COMMENT 'Effective end (NULL = always)',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted       TINYINT  NOT NULL DEFAULT 0
) COMMENT='Feature flag definitions';

CREATE TABLE feature_flag_rule (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    flag_id       BIGINT       NOT NULL COMMENT 'FK → feature_flag.id',
    scope         ENUM('global','tenant','user','kb','environment') NOT NULL,
    scope_value   VARCHAR(200) DEFAULT NULL COMMENT 'tenant_id / user_id / kb_id / env name',
    enabled       BOOLEAN NOT NULL,
    percentage    INT          DEFAULT NULL,
    whitelist     TEXT         DEFAULT NULL,
    blacklist     TEXT         DEFAULT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted       TINYINT  NOT NULL DEFAULT 0,
    INDEX idx_ff_rule_flag (flag_id),
    INDEX idx_ff_rule_scope (scope, scope_value)
) COMMENT='Per-scope override rules for a flag';

CREATE TABLE feature_flag_audit_log (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    flag_id       BIGINT       NOT NULL,
    flag_key      VARCHAR(100) NOT NULL,
    action        ENUM('create','update','delete') NOT NULL,
    operator_id   BIGINT       DEFAULT NULL,
    old_value     TEXT         DEFAULT NULL COMMENT 'JSON snapshot before change',
    new_value     TEXT         DEFAULT NULL COMMENT 'JSON snapshot after change',
    reason        VARCHAR(500) DEFAULT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ff_audit_flag (flag_id),
    INDEX idx_ff_audit_time (created_at)
) COMMENT='Audit trail for flag changes';

-- Seed initial flags (all disabled by default)
INSERT IGNORE INTO feature_flag (flag_key, flag_type, description, enabled) VALUES
('agent.enabled',              'boolean', 'Master switch for agent capabilities',           FALSE),
('agent.write_tools.enabled',  'boolean', 'Allow agent to invoke write/mutation tools',     FALSE),
('agent.web_search.enabled',   'boolean', 'Allow agent to use external web search',         FALSE),
('agent.multi_agent.enabled',  'boolean', 'Enable multi-agent workflow orchestration',      FALSE),
('rag.graph.enabled',          'boolean', 'Enable GraphRAG knowledge graph retrieval',      FALSE),
('rag.reranker.enabled',       'boolean', 'Enable second-stage reranking (cross-encoder)',  FALSE),
('approval.required_for_write','boolean', 'Require human approval before write-tool exec',   TRUE);
