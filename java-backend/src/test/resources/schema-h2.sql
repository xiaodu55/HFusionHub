-- =====================================================
-- HFusionHub —H2 Test Schema (MySQL-compatible mode)
-- Combines V1–V7 migrations into a single H2-compatible DDL.
-- Used by Spring's sql.init when Flyway is disabled in tests.
-- =====================================================

-- =====================================================
-- 用户表(sys_user)
-- =====================================================
CREATE TABLE IF NOT EXISTS sys_user (
    id BIGINT NOT NULL AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(100) NOT NULL,
    nickname VARCHAR(50) DEFAULT NULL,
    email VARCHAR(100) DEFAULT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    avatar VARCHAR(500) DEFAULT NULL,
    theme_preference VARCHAR(16) DEFAULT NULL,
    oauth_provider VARCHAR(32) DEFAULT NULL,
    oauth_subject VARCHAR(255) DEFAULT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    status SMALLINT NOT NULL DEFAULT 0,
    last_login_time TIMESTAMP DEFAULT NULL,
    last_login_ip VARCHAR(50) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE (username),
    UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_sys_user_phone ON sys_user (phone);
CREATE INDEX IF NOT EXISTS idx_sys_user_status ON sys_user (status);
CREATE INDEX IF NOT EXISTS idx_sys_user_created_at ON sys_user (created_at);

-- =====================================================
-- 知识库表 (knowledge_base)
-- =====================================================
CREATE TABLE IF NOT EXISTS knowledge_base (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    user_id BIGINT NOT NULL,
    status SMALLINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recycled_at TIMESTAMP DEFAULT NULL,
    recycle_expires_at TIMESTAMP DEFAULT NULL,
    deleted SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES sys_user (id)
);

CREATE INDEX IF NOT EXISTS idx_kb_user_id ON knowledge_base (user_id);
CREATE INDEX IF NOT EXISTS idx_kb_status ON knowledge_base (status);
CREATE INDEX IF NOT EXISTS idx_kb_created_at ON knowledge_base (created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_recycle_expires ON knowledge_base (deleted, recycle_expires_at);

-- =====================================================
-- 文档表(document)
-- =====================================================
CREATE TABLE IF NOT EXISTS document (
    id BIGINT NOT NULL AUTO_INCREMENT,
    knowledge_base_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    content CLOB DEFAULT NULL,
    file_path VARCHAR(500) DEFAULT NULL,
    file_type VARCHAR(20) DEFAULT NULL,
    file_size BIGINT DEFAULT NULL,
    chunk_count INT DEFAULT 0,
    status SMALLINT NOT NULL DEFAULT 0,
    error_message VARCHAR(500) DEFAULT NULL,
    visibility VARCHAR(20) NOT NULL DEFAULT 'general',
    processed_at DATETIME DEFAULT NULL,
    recycled_at DATETIME DEFAULT NULL,
    recycle_expires_at DATETIME DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_base (id)
);

CREATE INDEX IF NOT EXISTS idx_doc_kb_id ON document (knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_doc_status ON document (status);
CREATE INDEX IF NOT EXISTS idx_doc_created_at ON document (created_at);
CREATE INDEX IF NOT EXISTS idx_document_recycle_expires ON document (deleted, recycle_expires_at);

-- =====================================================
-- 对话表(conversation)
-- =====================================================
CREATE TABLE IF NOT EXISTS conversation (
    id BIGINT NOT NULL AUTO_INCREMENT,
    knowledge_base_id BIGINT DEFAULT NULL,
    prompt_template_id BIGINT DEFAULT NULL,
    user_id BIGINT NOT NULL,
    title VARCHAR(200) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES sys_user (id),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_base (id)
);

CREATE INDEX IF NOT EXISTS idx_conv_user_id ON conversation (user_id);
CREATE INDEX IF NOT EXISTS idx_conv_kb_id ON conversation (knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_conv_prompt_template ON conversation (prompt_template_id);
CREATE INDEX IF NOT EXISTS idx_conv_created_at ON conversation (created_at);

-- =====================================================
-- Prompt templates —V16
-- =====================================================
CREATE TABLE IF NOT EXISTS prompt_template (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    deleted TINYINT NOT NULL DEFAULT 0,
    -- 与 V45 对齐：活跃记录按 (user_id, name) 唯一，回收站允许重名
    active_name VARCHAR(100) GENERATED ALWAYS AS (CASE WHEN deleted = 0 THEN name END),
    description VARCHAR(500) DEFAULT NULL,
    content CLOB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    version INT NOT NULL DEFAULT 1,
    recycled_at TIMESTAMP DEFAULT NULL,
    recycle_expires_at TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (user_id, active_name),
    FOREIGN KEY (user_id) REFERENCES sys_user (id)
);
CREATE INDEX IF NOT EXISTS idx_prompt_template_user_status ON prompt_template (user_id, status, updated_at);

-- =====================================================
-- Prompt template version history —V17
-- =====================================================
CREATE TABLE IF NOT EXISTS prompt_template_version (
    id BIGINT NOT NULL AUTO_INCREMENT,
    template_id BIGINT NOT NULL,
    version INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    content CLOB NOT NULL,
    status VARCHAR(20) NOT NULL,
    operation VARCHAR(20) NOT NULL,
    operator_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (template_id) REFERENCES prompt_template (id) ON DELETE CASCADE,
    FOREIGN KEY (operator_id) REFERENCES sys_user (id)
);

CREATE INDEX IF NOT EXISTS idx_ptv_template_version ON prompt_template_version (template_id, version);

-- =====================================================
-- 消息表(message) —includes V4 request_id column
-- =====================================================
CREATE TABLE IF NOT EXISTS message (
    id BIGINT NOT NULL AUTO_INCREMENT,
    conversation_id BIGINT NOT NULL,
    role VARCHAR(20) NOT NULL,
    content CLOB NOT NULL,
    token_count INT DEFAULT 0,
    model VARCHAR(50) DEFAULT NULL,
    sources VARCHAR(4000) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    request_id VARCHAR(64) DEFAULT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (conversation_id) REFERENCES conversation (id)
);

CREATE INDEX IF NOT EXISTS idx_msg_conv_id ON message (conversation_id);
CREATE INDEX IF NOT EXISTS idx_msg_created_at ON message (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uk_msg_request_id ON message (request_id);
CREATE INDEX IF NOT EXISTS idx_msg_conv_created_id ON message (conversation_id, created_at, id);

-- =====================================================
-- 工具表(tool)
-- =====================================================
CREATE TABLE IF NOT EXISTS tool (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    parameters VARCHAR(4000) DEFAULT NULL,
    handler VARCHAR(100) NOT NULL,
    status SMALLINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_tool_status ON tool (status);

-- =====================================================
-- 文档索引任务表(document_index_job) —V2
-- =====================================================
CREATE TABLE IF NOT EXISTS document_index_job (
    id BIGINT NOT NULL AUTO_INCREMENT,
    document_id BIGINT NOT NULL,
    knowledge_base_id BIGINT NOT NULL,
    index_version VARCHAR(64) NOT NULL,
    embedding_model VARCHAR(100) DEFAULT NULL,
    status VARCHAR(20) NOT NULL,
    attempt INT NOT NULL DEFAULT 1,
    chunk_count INT NOT NULL DEFAULT 0,
    error_message VARCHAR(1000) DEFAULT NULL,
    started_at TIMESTAMP DEFAULT NULL,
    completed_at TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE (document_id, index_version),
    FOREIGN KEY (document_id) REFERENCES document (id)
);

CREATE INDEX IF NOT EXISTS idx_dij_document_status ON document_index_job (document_id, status);
CREATE INDEX IF NOT EXISTS idx_dij_status_created ON document_index_job (status, created_at);

-- =====================================================
-- 文档分块元数据表 (document_chunk) —V2
-- =====================================================
CREATE TABLE IF NOT EXISTS document_chunk (
    chunk_id VARCHAR(128) NOT NULL,
    document_id BIGINT NOT NULL,
    knowledge_base_id BIGINT NOT NULL,
    index_version VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL,
    block_type VARCHAR(32) DEFAULT NULL,
    outline_path VARCHAR(4000) DEFAULT NULL,
    content_excerpt VARCHAR(1000) DEFAULT NULL,
    char_count INT DEFAULT NULL,
    metadata VARCHAR(4000) DEFAULT NULL,
    PRIMARY KEY (chunk_id),
    FOREIGN KEY (document_id) REFERENCES document (id)
);

CREATE INDEX IF NOT EXISTS idx_chunk_doc_version ON document_chunk (document_id, index_version);
CREATE INDEX IF NOT EXISTS idx_chunk_kb_doc ON document_chunk (knowledge_base_id, document_id);

-- =====================================================
-- 异步删除任务表(deletion_task) —V3
-- =====================================================
CREATE TABLE IF NOT EXISTS deletion_task (
    id BIGINT NOT NULL AUTO_INCREMENT,
    task_type VARCHAR(32) NOT NULL,
    target_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    step VARCHAR(64) DEFAULT NULL,
    step_index INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 5,
    retry_count INT NOT NULL DEFAULT 0,
    error_message VARCHAR(2000) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_dt_status_created ON deletion_task (status, created_at);
CREATE INDEX IF NOT EXISTS idx_dt_target ON deletion_task (task_type, target_id);

-- =====================================================
-- Flyway schema history —required for baseline-on-migrate
-- =====================================================
CREATE TABLE IF NOT EXISTS flyway_schema_history (
    installed_rank INT NOT NULL,
    version VARCHAR(50),
    description VARCHAR(200) NOT NULL,
    type VARCHAR(20) NOT NULL,
    script VARCHAR(1000) NOT NULL,
    checksum INT,
    installed_by VARCHAR(100) NOT NULL,
    installed_on TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    execution_time INT NOT NULL,
    success SMALLINT NOT NULL,
    PRIMARY KEY (installed_rank)
);

CREATE INDEX IF NOT EXISTS idx_flyway_history_success ON flyway_schema_history (success);

-- =====================================================
-- Agent 任务表(agent_task) —V10 + V13
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_task (
    id                BIGINT NOT NULL AUTO_INCREMENT,
    request_id        VARCHAR(64) NOT NULL,
    user_id           BIGINT NOT NULL,
    conversation_id   BIGINT NOT NULL,
    knowledge_base_id BIGINT DEFAULT NULL,
    query             CLOB NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'pending',
    current_run_id    BIGINT DEFAULT NULL,
    dead_letter_reason VARCHAR(500) DEFAULT NULL,
    dead_letter_at    TIMESTAMP DEFAULT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (request_id),
    FOREIGN KEY (user_id) REFERENCES sys_user (id),
    FOREIGN KEY (conversation_id) REFERENCES conversation (id)
);

CREATE INDEX IF NOT EXISTS idx_task_user_status ON agent_task (user_id, status);
CREATE INDEX IF NOT EXISTS idx_task_conv ON agent_task (conversation_id);
CREATE INDEX IF NOT EXISTS idx_task_created_at ON agent_task (created_at);
CREATE INDEX IF NOT EXISTS idx_task_status_updated ON agent_task (status, updated_at);

-- =====================================================
-- Agent 运行记录表(agent_run) —V10 + V13
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_run (
    id                BIGINT NOT NULL AUTO_INCREMENT,
    task_id           BIGINT NOT NULL,
    run_uuid          VARCHAR(36) NOT NULL,
    attempt_number    INT NOT NULL DEFAULT 1,
    status            VARCHAR(20) NOT NULL DEFAULT 'pending',
    scheduled_at      TIMESTAMP DEFAULT NULL,
    lease_holder      VARCHAR(64) DEFAULT NULL,
    lease_expires_at  TIMESTAMP DEFAULT NULL,
    heartbeat_at      TIMESTAMP DEFAULT NULL,
    dispatch_count    INT NOT NULL DEFAULT 1,
    model             VARCHAR(50) DEFAULT NULL,
    style             VARCHAR(20) DEFAULT 'detailed',
    max_tool_steps    INT DEFAULT 5,
    token_usage       VARCHAR(4000) DEFAULT NULL,
    tool_calls_count  INT DEFAULT 0,
    error_code        VARCHAR(50) DEFAULT NULL,
    error_detail      CLOB DEFAULT NULL,
    failed_tool       VARCHAR(50) DEFAULT NULL,
    started_at        TIMESTAMP DEFAULT NULL,
    completed_at      TIMESTAMP DEFAULT NULL,
    duration_ms       BIGINT DEFAULT 0,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (run_uuid),
    FOREIGN KEY (task_id) REFERENCES agent_task (id)
);

CREATE INDEX IF NOT EXISTS idx_run_task_id ON agent_run (task_id);
CREATE INDEX IF NOT EXISTS idx_run_status ON agent_run (status);
CREATE INDEX IF NOT EXISTS idx_run_queue ON agent_run (status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_run_lease ON agent_run (lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_run_holder ON agent_run (lease_holder);
-- V77 (S4): 并发双重入队守卫
CREATE UNIQUE INDEX IF NOT EXISTS uk_run_task_attempt ON agent_run (task_id, attempt_number);

-- =====================================================
-- Agent 步骤记录表(agent_step) —V10
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_step (
    id              BIGINT NOT NULL AUTO_INCREMENT,
    run_id          BIGINT NOT NULL,
    sequence        INT NOT NULL DEFAULT 0,
    step_type       VARCHAR(30) NOT NULL,
    action          VARCHAR(50) DEFAULT NULL,
    input_summary   CLOB DEFAULT NULL,
    output_summary  CLOB DEFAULT NULL,
    sources         VARCHAR(4000) DEFAULT NULL,
    duration_ms     BIGINT DEFAULT 0,
    error_code      VARCHAR(50) DEFAULT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (run_id) REFERENCES agent_run (id)
);

CREATE INDEX IF NOT EXISTS idx_step_run_seq ON agent_step (run_id, sequence);

-- =====================================================
-- Agent 审批表(agent_approval) —V11
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_approval (
    id                BIGINT NOT NULL AUTO_INCREMENT,
    approval_id       VARCHAR(36) NOT NULL,
    task_id           BIGINT NOT NULL,
    run_id            BIGINT NOT NULL,
    user_id           BIGINT NOT NULL,
    user_role         VARCHAR(20) DEFAULT 'user',
    trace_id          VARCHAR(64) DEFAULT NULL,
    tool_name         VARCHAR(50) NOT NULL,
    risk_level        VARCHAR(32) DEFAULT 'read_only',
    tool_input_hash   VARCHAR(64) NOT NULL,
    execution_token   VARCHAR(64) DEFAULT NULL,
    execution_token_status VARCHAR(16) DEFAULT 'none',
    execution_token_issued_at TIMESTAMP DEFAULT NULL,
    execution_token_consumed_at TIMESTAMP DEFAULT NULL,
    tool_input        CLOB DEFAULT NULL,
    arguments_summary VARCHAR(1000) DEFAULT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'pending',
    decided_by        BIGINT DEFAULT NULL,
    decided_at        VARCHAR(20) DEFAULT NULL,
    reason            VARCHAR(500) DEFAULT NULL,
    expires_at        TIMESTAMP NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (approval_id),
    FOREIGN KEY (task_id) REFERENCES agent_task (id),
    FOREIGN KEY (run_id) REFERENCES agent_run (id)
);

CREATE INDEX IF NOT EXISTS idx_approval_task ON agent_approval (task_id);
CREATE INDEX IF NOT EXISTS idx_approval_user_status ON agent_approval (user_id, status);

-- =====================================================
-- Agent 状态事件表 (agent_status_event) —V13
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_status_event (
    id          BIGINT NOT NULL AUTO_INCREMENT,
    task_id     BIGINT NOT NULL,
    run_id      BIGINT DEFAULT NULL,
    event_type  VARCHAR(40) NOT NULL,
    status      VARCHAR(20) DEFAULT NULL,
    payload     VARCHAR(4000) DEFAULT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (task_id) REFERENCES agent_task (id)
);

CREATE INDEX IF NOT EXISTS idx_ase_task ON agent_status_event (task_id, id);

-- =====================================================
-- Agent 恢复审计表(agent_recovery_event) —V13
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_recovery_event (
    id          BIGINT NOT NULL AUTO_INCREMENT,
    run_id      BIGINT NOT NULL,
    task_id     BIGINT NOT NULL,
    event_type  VARCHAR(40) NOT NULL,
    detail      VARCHAR(1000) DEFAULT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_are_run ON agent_recovery_event (run_id);
CREATE INDEX IF NOT EXISTS idx_are_created ON agent_recovery_event (created_at);

-- =====================================================
-- Prompt test sets —V18
-- =====================================================
CREATE TABLE IF NOT EXISTS prompt_test_set (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (user_id, name),
    FOREIGN KEY (user_id) REFERENCES sys_user (id)
);

CREATE INDEX IF NOT EXISTS idx_pts_user_updated ON prompt_test_set (user_id, updated_at);

CREATE TABLE IF NOT EXISTS prompt_test_case (
    id BIGINT NOT NULL AUTO_INCREMENT,
    set_id BIGINT NOT NULL,
    question VARCHAR(4000) NOT NULL,
    variables VARCHAR(4000) DEFAULT NULL,
    expected_keywords VARCHAR(4000) DEFAULT NULL,
    required_document_ids VARCHAR(4000) DEFAULT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (set_id) REFERENCES prompt_test_set (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ptc_set_order ON prompt_test_case (set_id, sort_order);

-- =====================================================
-- Prompt test set run history —V19
-- =====================================================
CREATE TABLE IF NOT EXISTS prompt_test_set_run (
    id BIGINT NOT NULL AUTO_INCREMENT,
    set_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    template_id BIGINT DEFAULT NULL,
    template_version INT DEFAULT NULL,
    template_name VARCHAR(100) DEFAULT NULL,
    template_content VARCHAR(4000) DEFAULT NULL,
    knowledge_base_id BIGINT DEFAULT NULL,
    total_cases INT NOT NULL DEFAULT 0,
    success_count INT NOT NULL DEFAULT 0,
    failure_count INT NOT NULL DEFAULT 0,
    pass_count INT NOT NULL DEFAULT 0,
    total_elapsed_ms BIGINT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'succeeded',
    attempt_number INT NOT NULL DEFAULT 1,
    progress_count INT NOT NULL DEFAULT 0,
    execution_token VARCHAR(64) DEFAULT NULL,
    error_message VARCHAR(2000) DEFAULT NULL,
    scheduled_at TIMESTAMP DEFAULT NULL,
    started_at TIMESTAMP DEFAULT NULL,
    heartbeat_at TIMESTAMP DEFAULT NULL,
    completed_at TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (set_id) REFERENCES prompt_test_set (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES sys_user (id)
);

CREATE INDEX IF NOT EXISTS idx_ptsr_set_created ON prompt_test_set_run (set_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ptsr_status_scheduled ON prompt_test_set_run (status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_ptsr_status_heartbeat ON prompt_test_set_run (status, heartbeat_at);

CREATE TABLE IF NOT EXISTS prompt_test_case_result (
    id BIGINT NOT NULL AUTO_INCREMENT,
    run_id BIGINT NOT NULL,
    case_id BIGINT NOT NULL,
    question VARCHAR(4000) NOT NULL,
    rendered_template VARCHAR(4000) DEFAULT NULL,
    content VARCHAR(4000) DEFAULT NULL,
    model VARCHAR(100) DEFAULT NULL,
    token_count INT NOT NULL DEFAULT 0,
    token_usage VARCHAR(4000) DEFAULT NULL,
    sources VARCHAR(4000) DEFAULT NULL,
    elapsed_ms BIGINT NOT NULL DEFAULT 0,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    passed BOOLEAN NOT NULL DEFAULT TRUE,
    pass_notes VARCHAR(4000) DEFAULT NULL,
    error VARCHAR(1000) DEFAULT NULL,
    execution_token VARCHAR(64) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (run_id) REFERENCES prompt_test_set_run (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ptcr_run ON prompt_test_case_result (run_id);
CREATE INDEX IF NOT EXISTS idx_ptcr_run_token ON prompt_test_case_result (run_id, execution_token);
CREATE INDEX IF NOT EXISTS idx_ptcr_case ON prompt_test_case_result (case_id);

-- =====================================================
-- Feature Flags (V24)
-- =====================================================
CREATE TABLE IF NOT EXISTS feature_flag (
    id            BIGINT NOT NULL AUTO_INCREMENT,
    flag_key      VARCHAR(100) NOT NULL,
    flag_type     VARCHAR(20) NOT NULL DEFAULT 'boolean',
    description   VARCHAR(500) DEFAULT NULL,
    enabled       BOOLEAN NOT NULL DEFAULT FALSE,
    percentage    INT          DEFAULT NULL,
    whitelist     TEXT         DEFAULT NULL,
    blacklist     TEXT         DEFAULT NULL,
    start_time    TIMESTAMP    DEFAULT NULL,
    end_time      TIMESTAMP    DEFAULT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted       TINYINT  NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE (flag_key)
);

CREATE TABLE IF NOT EXISTS feature_flag_rule (
    id            BIGINT NOT NULL AUTO_INCREMENT,
    flag_id       BIGINT       NOT NULL,
    scope         VARCHAR(20)  NOT NULL,
    scope_value   VARCHAR(200) DEFAULT NULL,
    enabled       BOOLEAN      DEFAULT NULL,
    percentage    INT          DEFAULT NULL,
    whitelist     TEXT         DEFAULT NULL,
    blacklist     TEXT         DEFAULT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted       TINYINT  NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    FOREIGN KEY (flag_id) REFERENCES feature_flag (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ff_rule_flag ON feature_flag_rule (flag_id);
CREATE INDEX IF NOT EXISTS idx_ff_rule_scope ON feature_flag_rule (scope, scope_value);

CREATE TABLE IF NOT EXISTS feature_flag_audit_log (
    id            BIGINT NOT NULL AUTO_INCREMENT,
    flag_id       BIGINT       NOT NULL,
    flag_key      VARCHAR(100) NOT NULL,
    action        VARCHAR(20)  NOT NULL,
    operator_id   BIGINT       DEFAULT NULL,
    old_value     TEXT         DEFAULT NULL,
    new_value     TEXT         DEFAULT NULL,
    reason        VARCHAR(500) DEFAULT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_ff_audit_flag ON feature_flag_audit_log (flag_id);
CREATE INDEX IF NOT EXISTS idx_ff_audit_time ON feature_flag_audit_log (created_at);

-- =====================================================
-- 工具插件表(plugin) —V29
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin (
    id                     BIGINT       NOT NULL AUTO_INCREMENT,
    plugin_id              VARCHAR(36)  NOT NULL,
    name                   VARCHAR(100) NOT NULL,
    display_name           VARCHAR(200) DEFAULT NULL,
    description            CLOB         DEFAULT NULL,
    version                VARCHAR(32)  NOT NULL,
    author                 VARCHAR(100) DEFAULT NULL,
    author_email           VARCHAR(200) DEFAULT NULL,
    license                VARCHAR(64)  DEFAULT NULL,
    min_hfusionhub_version VARCHAR(32)  DEFAULT NULL,
    max_hfusionhub_version VARCHAR(32)  DEFAULT NULL,
    icon_url               VARCHAR(500) DEFAULT NULL,
    source                 VARCHAR(32)  NOT NULL DEFAULT 'local',
    plugin_kind            VARCHAR(24)  NOT NULL DEFAULT 'package',
    status                 VARCHAR(20)  NOT NULL DEFAULT 'active',
    manifest_hash          VARCHAR(64)  DEFAULT NULL,
    artifact_path          VARCHAR(500) DEFAULT NULL,
    artifact_hash          VARCHAR(64)  DEFAULT NULL,
    sandbox_config         CLOB         DEFAULT NULL,
    permissions            CLOB         DEFAULT NULL,
    tool_specs_json        CLOB         DEFAULT NULL,
    enabled                TINYINT      NOT NULL DEFAULT 1,
    installed_by           BIGINT       DEFAULT NULL,
    installed_at           TIMESTAMP    NULL DEFAULT NULL,
    created_at             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted                TINYINT      NOT NULL DEFAULT 0,
    canary_weight          DECIMAL(3,2) DEFAULT 0.00,
    circuit_open_until     TIMESTAMP    NULL,
    previous_version       VARCHAR(32)  DEFAULT NULL,
    health_status          VARCHAR(16)  DEFAULT 'unknown',
    last_health_check      TIMESTAMP    NULL,
    sbom_json              TEXT         DEFAULT NULL,
    vulnerability_status   VARCHAR(16)  DEFAULT 'pending',
    last_scan_at           TIMESTAMP    NULL,
    container_image        VARCHAR(256) DEFAULT NULL,
    image_digest           VARCHAR(128) DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE (plugin_id),
    FOREIGN KEY (installed_by) REFERENCES sys_user (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_plugin_name ON plugin (name);
CREATE INDEX IF NOT EXISTS idx_plugin_status ON plugin (status);

-- =====================================================
-- 插件审计日志表(plugin_audit_log) —V29
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_audit_log (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    event_id    VARCHAR(36)  DEFAULT NULL,
    plugin_id   BIGINT       NOT NULL,
    plugin_name VARCHAR(100) DEFAULT NULL,
    action      VARCHAR(32)  NOT NULL,
    operator_id BIGINT       DEFAULT NULL,
    old_value   CLOB         DEFAULT NULL,
    new_value   CLOB         DEFAULT NULL,
    reason      VARCHAR(500) DEFAULT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (event_id),
    FOREIGN KEY (plugin_id) REFERENCES plugin (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_plugin_audit_plugin ON plugin_audit_log (plugin_id);
CREATE INDEX IF NOT EXISTS idx_plugin_audit_time ON plugin_audit_log (created_at);

-- =====================================================
-- 插件依赖表(plugin_dependency) —V29
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_dependency (
    id                 BIGINT       NOT NULL AUTO_INCREMENT,
    plugin_id          BIGINT       NOT NULL,
    dependency_name    VARCHAR(100) NOT NULL,
    dependency_version VARCHAR(32)  DEFAULT NULL,
    optional           TINYINT      NOT NULL DEFAULT 0,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (plugin_id) REFERENCES plugin (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_plugin_dep_plugin ON plugin_dependency (plugin_id);

-- =====================================================
-- 插件执行指标表(plugin_execution_metric) —V30
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_execution_metric (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plugin_id BIGINT NOT NULL,
    metric_name VARCHAR(128) NOT NULL,
    metric_value DOUBLE NOT NULL,
    labels TEXT DEFAULT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 插件健康检查日志表 (plugin_health_log) —V30
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_health_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plugin_id BIGINT NOT NULL,
    check_type VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    details TEXT DEFAULT NULL,
    duration_ms FLOAT DEFAULT NULL,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 插件版本历史表(plugin_version_history) —V30
-- =====================================================
CREATE TABLE IF NOT EXISTS plugin_version_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plugin_id BIGINT NOT NULL,
    version VARCHAR(32) NOT NULL,
    artifact_key VARCHAR(500) DEFAULT NULL,
    artifact_hash VARCHAR(64) DEFAULT NULL,
    manifest_json TEXT DEFAULT NULL,
    is_canary TINYINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- V32 —Tenant, Organization Member & Role-Permission
-- =====================================================
CREATE TABLE IF NOT EXISTS tenant (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    slug        VARCHAR(50) NOT NULL UNIQUE,
    plan_tier   VARCHAR(20) NOT NULL DEFAULT 'free',
    status      VARCHAR(20) NOT NULL DEFAULT 'active',
    created_by  BIGINT DEFAULT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted     TINYINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tenant_member (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    role        VARCHAR(20) NOT NULL DEFAULT 'member',
    joined_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted     TINYINT NOT NULL DEFAULT 0,
    UNIQUE (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS role_permission (
    role        VARCHAR(20) NOT NULL,
    permission  VARCHAR(100) NOT NULL,
    PRIMARY KEY (role, permission)
);

-- Seed role permissions (H2: simple INSERTs since table is freshly created)
INSERT INTO role_permission (role, permission) VALUES ('owner', 'kb:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'kb:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'kb:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'conversation:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'conversation:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'plugin:install') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'plugin:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'member:invite') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'member:remove') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'member:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'tenant:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'tenant:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'billing:view') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'quota:view') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('owner', 'quota:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'kb:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'kb:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'kb:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'conversation:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'conversation:delete') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'plugin:install') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'plugin:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'member:invite') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'member:remove') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'member:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'quota:view') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('admin', 'billing:view') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('member', 'kb:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('member', 'kb:manage') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('member', 'conversation:create') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('member', 'plugin:install') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('viewer', 'kb:read') ON DUPLICATE KEY UPDATE role = role;
INSERT INTO role_permission (role, permission) VALUES ('viewer', 'conversation:read') ON DUPLICATE KEY UPDATE role = role;

-- V34 —tenant_audit_log (global, not tenant-scoped)
CREATE TABLE IF NOT EXISTS tenant_audit_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    operator_id BIGINT NOT NULL,
    from_tenant BIGINT NOT NULL,
    to_tenant   BIGINT NOT NULL,
    action      VARCHAR(500) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Add tenant_id to sys_user (H2-compatible ALTER)
ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS platform_admin TINYINT DEFAULT 0;

-- Insert default tenant for tests
INSERT INTO tenant (id, name, slug, plan_tier, status) VALUES
    (1, 'Default', 'default', 'enterprise', 'active')
    ON DUPLICATE KEY UPDATE slug = 'default';

-- Insert default user for tests (FK target for conversation.user_id etc.)
INSERT INTO sys_user (id, username, password, nickname, role, status, tenant_id)
    VALUES (1, 'default-user', 'test', 'Default', 'user', 0, 1)
    ON DUPLICATE KEY UPDATE nickname = 'Default';

-- Add tenant_id column to existing H2 tables (only those created above)
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE conversation ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE agent_task ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE prompt_template ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE prompt_test_set ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE prompt_test_set_run ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE plugin ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE plugin_audit_log ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE document ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE message ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE agent_step ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;

-- V35 —usage ledger: usage_event + usage_reservation + usage_counter + tenant_quota
CREATE TABLE IF NOT EXISTS usage_event (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    meter       VARCHAR(32) NOT NULL,
    operation   VARCHAR(16) NOT NULL,
    request_id  VARCHAR(64) NOT NULL,
    window_key  VARCHAR(10) NOT NULL,
    amount      BIGINT NOT NULL DEFAULT 0,
    ref_type    VARCHAR(32),
    ref_id      VARCHAR(64),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_usage_request_op UNIQUE (tenant_id, meter, request_id, operation)
);
CREATE INDEX IF NOT EXISTS idx_usage_reservation ON usage_event (tenant_id, meter, request_id);
CREATE INDEX IF NOT EXISTS idx_usage_tenant_window ON usage_event (tenant_id, window_key);
CREATE INDEX IF NOT EXISTS idx_usage_meter_window ON usage_event (meter, window_key);

CREATE TABLE IF NOT EXISTS usage_reservation (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id       BIGINT NOT NULL,
    meter           VARCHAR(32) NOT NULL,
    request_id      VARCHAR(64) NOT NULL,
    window_key      VARCHAR(10) NOT NULL,
    reserved_amount BIGINT NOT NULL,
    actual_amount   BIGINT NOT NULL DEFAULT 0,
    state           VARCHAR(16) NOT NULL DEFAULT 'RESERVED',
    ref_type        VARCHAR(32),
    ref_id          VARCHAR(64),
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_reservation UNIQUE (tenant_id, meter, request_id)
);

CREATE TABLE IF NOT EXISTS usage_counter (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    meter       VARCHAR(32) NOT NULL,
    window_key  VARCHAR(10) NOT NULL,
    reserved    BIGINT NOT NULL DEFAULT 0,
    committed   BIGINT NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_counter UNIQUE (tenant_id, meter, window_key)
);

CREATE TABLE IF NOT EXISTS tenant_quota (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    meter       VARCHAR(32) NOT NULL,
    daily_limit BIGINT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_tenant_meter UNIQUE (tenant_id, meter)
);

-- =====================================================
-- V36: cost tracking
-- =====================================================
CREATE TABLE IF NOT EXISTS model_usage_record (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT,
    conversation_id BIGINT,
    agent_task_id BIGINT,
    model VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    latency_ms INT NOT NULL DEFAULT 0,
    request_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_mur_user ON model_usage_record (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_mur_tenant ON model_usage_record (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_mur_model ON model_usage_record (model, created_at);
CREATE INDEX IF NOT EXISTS idx_mur_request_type ON model_usage_record (request_type, created_at);

-- =====================================================
-- V37: webhook system
-- =====================================================
CREATE TABLE IF NOT EXISTS webhook_subscription (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT,
    name VARCHAR(200) NOT NULL,
    url VARCHAR(1000) NOT NULL,
    secret VARCHAR(200),
    events TEXT NOT NULL,
    is_active TINYINT NOT NULL DEFAULT 1,
    last_triggered_at TIMESTAMP,
    failure_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS webhook_delivery (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    subscription_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    response_status INT,
    response_body TEXT,
    duration_ms INT,
    success TINYINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wd_subscription ON webhook_delivery (subscription_id, created_at);

-- =====================================================
-- V38: evaluation gate results
-- =====================================================
CREATE TABLE IF NOT EXISTS evaluation_gate_result (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dataset_id BIGINT NOT NULL,
    run_id BIGINT NOT NULL,
    run_uuid VARCHAR(64) NOT NULL,
    passed TINYINT NOT NULL DEFAULT 0,
    accuracy DECIMAL(6,4),
    latency_p95 INT,
    token_cost DECIMAL(12,6),
    baseline_run_uuid VARCHAR(64),
    baseline_token_cost DECIMAL(12,6),
    criteria_json TEXT,
    details TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_egr_dataset ON evaluation_gate_result (dataset_id, created_at);

-- =====================================================
-- V12: agent evaluation (missing from H2 schema — added for gate tests)
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_evaluation_dataset (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    knowledge_base_id BIGINT,
    user_id BIGINT NOT NULL,
    dimensions TEXT,
    case_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_evaluation_case (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dataset_id BIGINT NOT NULL,
    query TEXT NOT NULL,
    expected_answer TEXT,
    expected_sources TEXT,
    privilege_test TEXT,
    metadata TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_evaluation_run (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dataset_id BIGINT NOT NULL,
    run_uuid VARCHAR(36) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    overall_score DECIMAL(6,4),
    dimension_scores TEXT,
    case_results TEXT,
    failed_case_ids TEXT,
    error_detail TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_eval_run_uuid ON agent_evaluation_run (run_uuid);

-- =====================================================
-- V46: per-user conversation model provider
-- =====================================================
CREATE TABLE IF NOT EXISTS user_model_config (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL DEFAULT 1,
    provider_type VARCHAR(32) NOT NULL,
    provider_name VARCHAR(100) NOT NULL,
    base_url VARCHAR(500) NOT NULL,
    model_name VARCHAR(160) NOT NULL,
    api_key_ciphertext CLOB,
    enabled TINYINT NOT NULL DEFAULT 1,
    last_test_status VARCHAR(20),
    last_test_message VARCHAR(500),
    last_tested_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_user_model_config_tenant_user UNIQUE (tenant_id, user_id)
);

-- =====================================================
-- V40 + V41 + V42: RAG intent tree（意图路由）
-- =====================================================
CREATE TABLE IF NOT EXISTS rag_intent_node (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL DEFAULT 1,
    parent_id BIGINT DEFAULT NULL,
    intent_code VARCHAR(64) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    level VARCHAR(20) NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'KB',
    knowledge_base_id BIGINT DEFAULT NULL,
    mcp_tool_id BIGINT DEFAULT NULL,
    top_k INT NOT NULL DEFAULT 5,
    route_config JSON DEFAULT NULL,
    enabled TINYINT NOT NULL DEFAULT 1,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE (user_id, intent_code, deleted),
    CONSTRAINT fk_rag_intent_kb_setnull FOREIGN KEY (knowledge_base_id)
        REFERENCES knowledge_base (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_intent_user_parent ON rag_intent_node (user_id, parent_id, deleted, sort_order);
CREATE INDEX IF NOT EXISTS idx_rag_intent_tenant_parent ON rag_intent_node (tenant_id, parent_id, deleted, sort_order);

-- =====================================================
-- V12: Agent 告警（规则 + 事件）
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_alert_rule (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    description TEXT DEFAULT NULL,
    user_id BIGINT DEFAULT NULL,
    metric_name VARCHAR(50) NOT NULL,
    comparison_operator VARCHAR(10) NOT NULL DEFAULT 'gte',
    threshold_value DECIMAL(12,4) NOT NULL,
    window_minutes INT NOT NULL DEFAULT 60,
    severity VARCHAR(10) NOT NULL DEFAULT 'warning',
    cooldown_minutes INT NOT NULL DEFAULT 60,
    enabled TINYINT NOT NULL DEFAULT 1,
    last_triggered_at TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS idx_alert_rule_user ON agent_alert_rule (user_id);
CREATE INDEX IF NOT EXISTS idx_alert_rule_metric ON agent_alert_rule (metric_name);

CREATE TABLE IF NOT EXISTS agent_alert_event (
    id BIGINT NOT NULL AUTO_INCREMENT,
    rule_id BIGINT NOT NULL,
    rule_name VARCHAR(200) NOT NULL,
    user_id BIGINT DEFAULT NULL,
    knowledge_base_id BIGINT DEFAULT NULL,
    severity VARCHAR(10) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    current_value DECIMAL(12,4) NOT NULL,
    threshold_value DECIMAL(12,4) NOT NULL,
    message TEXT NOT NULL,
    context JSON DEFAULT NULL,
    resolved TINYINT NOT NULL DEFAULT 0,
    resolved_at TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_alert_event_rule FOREIGN KEY (rule_id) REFERENCES agent_alert_rule (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_alert_event_rule ON agent_alert_event (rule_id);
CREATE INDEX IF NOT EXISTS idx_alert_event_created ON agent_alert_event (created_at);

-- =====================================================
-- V43: RAG 回答反馈
-- =====================================================
CREATE TABLE IF NOT EXISTS rag_answer_feedback (
    id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    conversation_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    knowledge_base_id BIGINT DEFAULT NULL,
    rating VARCHAR(8) NOT NULL,
    reason VARCHAR(500) DEFAULT NULL,
    expected_answer TEXT DEFAULT NULL,
    evaluation_case_id BIGINT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE (user_id, message_id),
    CONSTRAINT fk_rag_feedback_user FOREIGN KEY (user_id) REFERENCES sys_user (id),
    CONSTRAINT fk_rag_feedback_conversation FOREIGN KEY (conversation_id) REFERENCES conversation (id) ON DELETE CASCADE,
    CONSTRAINT fk_rag_feedback_message FOREIGN KEY (message_id) REFERENCES message (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rag_feedback_tenant_created ON rag_answer_feedback (tenant_id, created_at);

-- =====================================================
-- 应用发布的 API Key (V52)
-- =====================================================
CREATE TABLE IF NOT EXISTS app (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL DEFAULT 1,
    knowledge_base_id BIGINT DEFAULT NULL,
    prompt_template_id BIGINT DEFAULT NULL,
    model VARCHAR(200) DEFAULT NULL,
    style VARCHAR(20) NOT NULL DEFAULT 'detailed',
    status TINYINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_app_user ON app (user_id);
CREATE INDEX IF NOT EXISTS idx_app_tenant ON app (tenant_id);

CREATE TABLE IF NOT EXISTS app_api_key (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    app_id BIGINT NOT NULL,
    name VARCHAR(100) DEFAULT NULL,
    key_hash VARCHAR(64) NOT NULL,
    key_prefix VARCHAR(12) NOT NULL,
    enabled TINYINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_apikey_app ON app_api_key (app_id);
CREATE INDEX IF NOT EXISTS idx_apikey_hash ON app_api_key (key_hash);

CREATE TABLE IF NOT EXISTS app_call_log (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    app_id BIGINT NOT NULL,
    api_key_id BIGINT DEFAULT NULL,
    user_id BIGINT DEFAULT NULL,
    tenant_id BIGINT NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'ok',
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_call_app ON app_call_log (app_id, created_at);
CREATE INDEX IF NOT EXISTS idx_call_key ON app_call_log (api_key_id);

-- =====================================================
-- 知识库共享 (V53)
-- =====================================================
CREATE TABLE IF NOT EXISTS kb_share (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    knowledge_base_id BIGINT NOT NULL,
    owner_user_id BIGINT NOT NULL,
    shared_user_id BIGINT NOT NULL,
    permission VARCHAR(20) NOT NULL DEFAULT 'read',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_share_user ON kb_share (shared_user_id);

-- =====================================================
-- 操作审计日志 (V54)
-- =====================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    operator_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL DEFAULT 1,
    action VARCHAR(50) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(64) DEFAULT NULL,
    detail VARCHAR(500) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_operator ON audit_log (operator_id, created_at);

-- =====================================================
-- 招投标垂直化 (V61-V65)
-- =====================================================
-- V65: 知识库分类
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS category VARCHAR(32) DEFAULT 'general';

-- V61: 投标项目
CREATE TABLE IF NOT EXISTS bid_project (
    id BIGINT NOT NULL AUTO_INCREMENT,
    knowledge_base_id BIGINT NOT NULL,
    tender_number VARCHAR(128) DEFAULT NULL,
    title VARCHAR(255) NOT NULL,
    budget DECIMAL(18,2) DEFAULT NULL,
    deadline VARCHAR(64) DEFAULT NULL,
    bid_bond VARCHAR(64) DEFAULT NULL,
    opening_date TIMESTAMP DEFAULT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'interpreting',
    created_by BIGINT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS idx_bid_project_kb ON bid_project (knowledge_base_id);

-- V62: 招标结构化要素
CREATE TABLE IF NOT EXISTS tender_element (
    id BIGINT NOT NULL AUTO_INCREMENT,
    project_id BIGINT NOT NULL,
    element_key VARCHAR(64) NOT NULL,
    element_value CLOB DEFAULT NULL,
    evidence_chunk_ids CLOB DEFAULT NULL,
    confidence DECIMAL(5,4) DEFAULT NULL,
    source_clause CLOB DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE (project_id, element_key)
);
CREATE INDEX IF NOT EXISTS idx_tender_element_project ON tender_element (project_id);

-- V63: 招标评分办法
CREATE TABLE IF NOT EXISTS bid_scoring_method (
    id BIGINT NOT NULL AUTO_INCREMENT,
    project_id BIGINT NOT NULL,
    method_type VARCHAR(32) NOT NULL,
    points_json CLOB DEFAULT NULL,
    total_score DECIMAL(8,2) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS idx_bid_scoring_project ON bid_scoring_method (project_id);

-- V64: 投标需求清单
CREATE TABLE IF NOT EXISTS bid_requirement (
    id BIGINT NOT NULL AUTO_INCREMENT,
    project_id BIGINT NOT NULL,
    category VARCHAR(32) NOT NULL,
    requirement CLOB NOT NULL,
    source_clause CLOB DEFAULT NULL,
    satisfied_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS idx_bid_requirement_project ON bid_requirement (project_id);

-- V66: 标书分节草稿
CREATE TABLE IF NOT EXISTS bid_draft (
    id BIGINT NOT NULL AUTO_INCREMENT,
    project_id BIGINT NOT NULL,
    section_key VARCHAR(32) NOT NULL,
    section_title VARCHAR(128) NOT NULL,
    content CLOB DEFAULT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'drafting',
    version INT NOT NULL DEFAULT 1,
    approved_by BIGINT DEFAULT NULL,
    created_by BIGINT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS idx_bid_draft_project ON bid_draft (project_id);

-- V67: 标书模板
CREATE TABLE IF NOT EXISTS bid_template (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(512) DEFAULT NULL,
    industry VARCHAR(64) DEFAULT NULL,
    section_defs CLOB NOT NULL,
    is_active TINYINT NOT NULL DEFAULT 1,
    created_by BIGINT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id)
);

-- V68: 废标风险自检报告
CREATE TABLE IF NOT EXISTS bid_check_report (
    id BIGINT NOT NULL AUTO_INCREMENT,
    project_id BIGINT NOT NULL,
    section_key VARCHAR(32) DEFAULT NULL,
    severity VARCHAR(16) NOT NULL DEFAULT 'warning',
    category VARCHAR(32) NOT NULL,
    finding CLOB NOT NULL,
    evidence CLOB DEFAULT NULL,
    suggested_fix CLOB DEFAULT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS idx_bid_check_project ON bid_check_report (project_id);

-- V69: 订阅套餐目录（平台级，tenant_id 可空）
CREATE TABLE IF NOT EXISTS bid_subscription (
    id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT DEFAULT NULL,
    plan_code VARCHAR(32) NOT NULL,
    plan_name VARCHAR(64) NOT NULL,
    plan_type VARCHAR(16) NOT NULL DEFAULT 'tier',
    price_cents BIGINT NOT NULL DEFAULT 0,
    max_projects INT NOT NULL DEFAULT 5,
    max_seats INT NOT NULL DEFAULT 5,
    char_quota BIGINT NOT NULL DEFAULT 100000,
    module_flags CLOB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_by BIGINT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    CONSTRAINT uk_subscription_code UNIQUE (plan_code)
);

-- V70: 租户套餐绑定（租户私有）
CREATE TABLE IF NOT EXISTS tenant_plan_binding (
    id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL,
    subscription_id BIGINT NOT NULL,
    start_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_at TIMESTAMP DEFAULT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_by BIGINT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    CONSTRAINT uk_binding_tenant_plan UNIQUE (tenant_id, subscription_id)
);

-- ============================================================
-- V82: HFusionData Analytics(与 V82__analytics_warehouse.sql 同步)
-- ============================================================
CREATE TABLE IF NOT EXISTS analytics_realtime_metrics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    window_start DATETIME NOT NULL,
    window_end DATETIME NOT NULL,
    tenant_id BIGINT NOT NULL,
    model VARCHAR(100) NOT NULL,
    request_count BIGINT NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    total_cost DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    avg_latency_ms BIGINT NOT NULL DEFAULT 0,
    max_latency_ms BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_rt_window UNIQUE (window_start, tenant_id, model)
);
CREATE TABLE IF NOT EXISTS ads_cost_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    stat_date DATE NOT NULL,
    call_count BIGINT NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    est_month_cost DECIMAL(12,2) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_ads_cost UNIQUE (tenant_id, stat_date)
);
CREATE TABLE IF NOT EXISTS ads_model_share (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    model VARCHAR(100) NOT NULL,
    stat_date DATE NOT NULL,
    call_count BIGINT NOT NULL DEFAULT 0,
    cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    cost_share DOUBLE NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_ads_model UNIQUE (tenant_id, model, stat_date)
);
CREATE TABLE IF NOT EXISTS ads_tenant_topn (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stat_date DATE NOT NULL,
    rank_no INT NOT NULL,
    tenant_id BIGINT NOT NULL,
    call_count BIGINT NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_ads_topn UNIQUE (stat_date, rank_no)
);
CREATE TABLE IF NOT EXISTS ads_tool_success (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    step_type VARCHAR(50) NOT NULL,
    stat_date DATE NOT NULL,
    step_count BIGINT NOT NULL DEFAULT 0,
    error_count BIGINT NOT NULL DEFAULT 0,
    success_rate DOUBLE NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_ads_tool UNIQUE (tenant_id, step_type, stat_date)
);
CREATE TABLE IF NOT EXISTS ads_eval_quality (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    stat_date DATE NOT NULL,
    eval_count BIGINT NOT NULL DEFAULT 0,
    avg_hit_ratio DOUBLE DEFAULT NULL,
    avg_ttft_ms BIGINT DEFAULT NULL,
    avg_latency_ms BIGINT DEFAULT NULL,
    failure_rate DOUBLE NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_ads_eval UNIQUE (tenant_id, stat_date)
);
CREATE TABLE IF NOT EXISTS bigdata_batch_run_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id BIGINT DEFAULT NULL,
    job_name VARCHAR(50) NOT NULL,
    batch_date DATE NOT NULL,
    command VARCHAR(1000) DEFAULT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    exit_code INT DEFAULT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME DEFAULT NULL,
    duration_ms BIGINT DEFAULT NULL,
    log_excerpt VARCHAR(2000) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- V84: 对话图片输入（message.images）
ALTER TABLE message ADD COLUMN IF NOT EXISTS images CLOB;

-- ═══ 第二十四批：schema-h2 真对齐 V84（V8/V9/V14/V26/V55/V56/V74/V76/V79/V83 补齐）═══
-- 翻译惯例：剥反引号/列注释/内联 INDEX/ENGINE 尾缀/FK；ON UPDATE CURRENT_TIMESTAMP
-- 不翻译（updatedAt 由 MyBatis-Plus 字段填充显式维护）。漂移基线已清空——零容忍。

-- V8+V14: memory_entry（长期记忆）
CREATE TABLE IF NOT EXISTS memory_entry (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    type VARCHAR(32) NOT NULL DEFAULT 'entity_fact',
    content TEXT NOT NULL,
    entities JSON NULL,
    conversation_id BIGINT NULL,
    knowledge_base_id BIGINT NULL,
    importance DOUBLE NOT NULL DEFAULT 0.5,
    expires_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tenant_id BIGINT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_entry (user_id);
CREATE INDEX IF NOT EXISTS idx_memory_conv ON memory_entry (conversation_id);
CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_entry (type);
CREATE INDEX IF NOT EXISTS idx_memory_user_expiry ON memory_entry (user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_memory_user_kb ON memory_entry (user_id, knowledge_base_id);

-- V55: note（用户笔记）
CREATE TABLE IF NOT EXISTS note (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT NULL,
    knowledge_base_id BIGINT NULL,
    conversation_id BIGINT NULL,
    message_id BIGINT NULL,
    title VARCHAR(200) NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'manual',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted TINYINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_note_user ON note (user_id, deleted, created_at);
CREATE INDEX IF NOT EXISTS idx_note_kb ON note (knowledge_base_id, deleted);
CREATE INDEX IF NOT EXISTS idx_note_tenant ON note (tenant_id);

-- V9: system_notice（系统公告）
CREATE TABLE IF NOT EXISTS system_notice (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(256) NOT NULL,
    content TEXT NOT NULL,
    level VARCHAR(16) NOT NULL DEFAULT 'info',
    publisher VARCHAR(64) NULL,
    scope VARCHAR(32) NOT NULL DEFAULT 'all',
    expires_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notice_created ON system_notice (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notice_expires ON system_notice (expires_at);

CREATE TABLE IF NOT EXISTS notice_recipient (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    notice_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    read_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_notice_user ON notice_recipient (notice_id, user_id);
CREATE INDEX IF NOT EXISTS idx_recipient_user_unread ON notice_recipient (user_id, is_read);

-- V79: eval_harness_runs（评估中枢运行记录）
CREATE TABLE IF NOT EXISTS eval_harness_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_file VARCHAR(160) NOT NULL,
    label VARCHAR(64) DEFAULT NULL,
    knowledge_base_id BIGINT DEFAULT NULL,
    top_k INT DEFAULT 5,
    record_count INT DEFAULT 0,
    requires_rag_count INT DEFAULT 0,
    judge_enabled TINYINT NOT NULL DEFAULT 0,
    judge_cases INT DEFAULT 0,
    overall JSON DEFAULT NULL,
    failed_case_ids JSON DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tenant_id BIGINT DEFAULT NULL,
    deleted TINYINT NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_eval_harness_run_file ON eval_harness_runs (run_file);
CREATE INDEX IF NOT EXISTS idx_eval_harness_created ON eval_harness_runs (created_at);
CREATE INDEX IF NOT EXISTS idx_eval_harness_tenant ON eval_harness_runs (tenant_id);

-- V83: table_lineage（表级血缘，平台口径 tenant_id=-1）
CREATE TABLE IF NOT EXISTS table_lineage (
    id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL DEFAULT -1,
    job_name VARCHAR(200) NOT NULL,
    layer VARCHAR(20) NOT NULL,
    source_table VARCHAR(200) NOT NULL,
    target_table VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uk_lineage_job_src_tgt UNIQUE (job_name, source_table, target_table)
);
CREATE INDEX IF NOT EXISTS idx_lineage_source ON table_lineage (source_table);
CREATE INDEX IF NOT EXISTS idx_lineage_target ON table_lineage (target_table);

-- V26 补齐：embedding 元数据列（实体含字段而 H2 缺失——插入路径未覆盖的真实风险）
ALTER TABLE document_chunk ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100) NULL;
ALTER TABLE document_chunk ADD COLUMN IF NOT EXISTS embedding_dimension INT NULL;
ALTER TABLE document_chunk ADD COLUMN IF NOT EXISTS embedding_version VARCHAR(64) NULL;
ALTER TABLE document_index_job ADD COLUMN IF NOT EXISTS embedding_dimension INT NULL;
ALTER TABLE document_index_job ADD COLUMN IF NOT EXISTS embedding_version VARCHAR(64) NULL;
-- V56 补齐：kb_share / app_api_key 的 tenant_id
ALTER TABLE kb_share ADD COLUMN IF NOT EXISTS tenant_id BIGINT NULL;
ALTER TABLE app_api_key ADD COLUMN IF NOT EXISTS tenant_id BIGINT NULL;
-- V76 补齐：tenant_plan_binding.deleted
ALTER TABLE tenant_plan_binding ADD COLUMN IF NOT EXISTS deleted TINYINT NOT NULL DEFAULT 0;
-- V74 补齐：存量表的租户索引（note 已随上表创建）
-- V32 补齐：上述 10 表的 tenant_id（BIGINT DEFAULT NULL，与生产 ADD COLUMN 一致）
ALTER TABLE agent_alert_event ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE agent_alert_rule ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE agent_evaluation_dataset ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE bid_check_report ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE bid_draft ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE bid_project ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE bid_requirement ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE bid_scoring_method ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE bid_template ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
ALTER TABLE tender_element ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT NULL;
-- V74 补齐：存量表的租户索引（置于文末：此时全部相关表均已创建）
CREATE INDEX IF NOT EXISTS idx_aar_tenant ON agent_alert_rule (tenant_id);
CREATE INDEX IF NOT EXISTS idx_aae_tenant ON agent_alert_event (tenant_id);
CREATE INDEX IF NOT EXISTS idx_aed_tenant ON agent_evaluation_dataset (tenant_id);
CREATE INDEX IF NOT EXISTS idx_pts_tenant ON prompt_test_set (tenant_id);
CREATE INDEX IF NOT EXISTS idx_ptsr_tenant ON prompt_test_set_run (tenant_id);
CREATE INDEX IF NOT EXISTS idx_acl_tenant ON app_call_log (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log (tenant_id);
CREATE INDEX IF NOT EXISTS idx_whs_tenant ON webhook_subscription (tenant_id);
