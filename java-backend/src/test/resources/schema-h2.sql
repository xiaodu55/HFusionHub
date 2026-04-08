-- =====================================================
-- HFusionHub �?H2 Test Schema (MySQL-compatible mode)
-- Combines V1–V7 migrations into a single H2-compatible DDL.
-- Used by Spring's sql.init when Flyway is disabled in tests.
-- =====================================================

-- =====================================================
-- 用户�?(sys_user)
-- =====================================================
CREATE TABLE IF NOT EXISTS sys_user (
    id BIGINT NOT NULL AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(100) NOT NULL,
    nickname VARCHAR(50) DEFAULT NULL,
    email VARCHAR(100) DEFAULT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    avatar VARCHAR(500) DEFAULT NULL,
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
    deleted SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES sys_user (id)
);

CREATE INDEX IF NOT EXISTS idx_kb_user_id ON knowledge_base (user_id);
CREATE INDEX IF NOT EXISTS idx_kb_status ON knowledge_base (status);
CREATE INDEX IF NOT EXISTS idx_kb_created_at ON knowledge_base (created_at);

-- =====================================================
-- 文档�?(document)
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
-- 对话�?(conversation)
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
-- Prompt templates �?V16
-- =====================================================
CREATE TABLE IF NOT EXISTS prompt_template (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    content CLOB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE (user_id, name),
    FOREIGN KEY (user_id) REFERENCES sys_user (id)
);
CREATE INDEX IF NOT EXISTS idx_prompt_template_user_status ON prompt_template (user_id, status, updated_at);

-- =====================================================
-- Prompt template version history �?V17
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
-- 消息�?(message) �?includes V4 request_id column
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
-- 工具�?(tool)
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
-- 文档索引任务�?(document_index_job) �?V2
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
-- 文档分块元数据表 (document_chunk) �?V2
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
-- 异步删除任务�?(deletion_task) �?V3
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
-- Flyway schema history �?required for baseline-on-migrate
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
-- Agent 任务�?(agent_task) �?V10 + V13
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
-- Agent 运行记录�?(agent_run) �?V10 + V13
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

-- =====================================================
-- Agent 步骤记录�?(agent_step) �?V10
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
-- Agent 审批�?(agent_approval) �?V11
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
-- Agent 状态事件表 (agent_status_event) �?V13
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
-- Agent 恢复审计�?(agent_recovery_event) �?V13
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
-- Prompt test sets �?V18
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
-- Prompt test set run history �?V19
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
-- 工具插件�?(plugin) �?V29
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
    status                 VARCHAR(20)  NOT NULL DEFAULT 'active',
    manifest_hash          VARCHAR(64)  DEFAULT NULL,
    artifact_path          VARCHAR(500) DEFAULT NULL,
    artifact_hash          VARCHAR(64)  DEFAULT NULL,
    sandbox_config         CLOB         DEFAULT NULL,
    permissions            CLOB         DEFAULT NULL,
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
-- 插件审计日志�?(plugin_audit_log) �?V29
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
-- 插件依赖�?(plugin_dependency) �?V29
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
-- 插件执行指标�?(plugin_execution_metric) �?V30
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
-- 插件健康检查日志表 (plugin_health_log) �?V30
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
-- 插件版本历史�?(plugin_version_history) �?V30
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
-- V32 �?Tenant, Organization Member & Role-Permission
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

-- V34 �?tenant_audit_log (global, not tenant-scoped)
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
ALTER TABLE plugin ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE plugin_audit_log ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE document ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE message ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE agent_step ADD COLUMN IF NOT EXISTS tenant_id BIGINT NOT NULL DEFAULT 1;

-- V35 �?usage ledger: usage_event + usage_reservation + usage_counter + tenant_quota
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
