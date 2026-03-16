-- =====================================================
-- HFusionHub — H2 Test Schema (MySQL-compatible mode)
-- Combines V1–V4 migrations into a single H2-compatible DDL.
-- Used by Spring's sql.init when Flyway is disabled in tests.
-- =====================================================

-- =====================================================
-- 用户表 (sys_user)
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
-- 文档表 (document)
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
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_base (id)
);

CREATE INDEX IF NOT EXISTS idx_doc_kb_id ON document (knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_doc_status ON document (status);
CREATE INDEX IF NOT EXISTS idx_doc_created_at ON document (created_at);

-- =====================================================
-- 对话表 (conversation)
-- =====================================================
CREATE TABLE IF NOT EXISTS conversation (
    id BIGINT NOT NULL AUTO_INCREMENT,
    knowledge_base_id BIGINT DEFAULT NULL,
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
CREATE INDEX IF NOT EXISTS idx_conv_created_at ON conversation (created_at);

-- =====================================================
-- 消息表 (message) — includes V4 request_id column
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
-- 工具表 (tool)
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
-- 文档索引任务表 (document_index_job) — V2
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
-- 文档分块元数据表 (document_chunk) — V2
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
-- 异步删除任务表 (deletion_task) — V3
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
-- Flyway schema history — required for baseline-on-migrate
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
-- Agent 任务表 (agent_task) — V10 + V13
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
-- Agent 运行记录表 (agent_run) — V10 + V13
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
-- Agent 步骤记录表 (agent_step) — V10
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
-- Agent 审批表 (agent_approval) — V11
-- =====================================================
CREATE TABLE IF NOT EXISTS agent_approval (
    id                BIGINT NOT NULL AUTO_INCREMENT,
    approval_id       VARCHAR(36) NOT NULL,
    task_id           BIGINT NOT NULL,
    run_id            BIGINT NOT NULL,
    user_id           BIGINT NOT NULL,
    tool_name         VARCHAR(50) NOT NULL,
    tool_input_hash   VARCHAR(64) NOT NULL,
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
-- Agent 状态事件表 (agent_status_event) — V13
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
-- Agent 恢复审计表 (agent_recovery_event) — V13
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
