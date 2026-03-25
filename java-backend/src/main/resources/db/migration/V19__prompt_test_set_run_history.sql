-- Prompt Test Set Run History — persist each batch run + per-case results,
-- so users can compare two template versions on the same test cases.

CREATE TABLE IF NOT EXISTS prompt_test_set_run (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    set_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    template_id BIGINT DEFAULT NULL,
    template_version INT DEFAULT NULL,
    template_name VARCHAR(100) DEFAULT NULL,
    template_content TEXT DEFAULT NULL,
    knowledge_base_id BIGINT DEFAULT NULL,
    total_cases INT NOT NULL DEFAULT 0,
    success_count INT NOT NULL DEFAULT 0,
    failure_count INT NOT NULL DEFAULT 0,
    total_elapsed_ms BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ptsr_set FOREIGN KEY (set_id) REFERENCES prompt_test_set(id) ON DELETE CASCADE,
    CONSTRAINT fk_ptsr_user FOREIGN KEY (user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ptsr_set_created ON prompt_test_set_run (set_id, created_at);

CREATE TABLE IF NOT EXISTS prompt_test_case_result (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    case_id BIGINT NOT NULL,
    question VARCHAR(4000) NOT NULL,
    rendered_template TEXT DEFAULT NULL,
    content MEDIUMTEXT DEFAULT NULL,
    model VARCHAR(100) DEFAULT NULL,
    token_count INT NOT NULL DEFAULT 0,
    token_usage TEXT DEFAULT NULL COMMENT 'Detailed token usage as JSON',
    sources TEXT DEFAULT NULL COMMENT 'Cited sources as JSON array',
    elapsed_ms BIGINT NOT NULL DEFAULT 0,
    success TINYINT(1) NOT NULL DEFAULT 1,
    error VARCHAR(1000) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ptcr_run FOREIGN KEY (run_id) REFERENCES prompt_test_set_run(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ptcr_run ON prompt_test_case_result (run_id);
CREATE INDEX idx_ptcr_case ON prompt_test_case_result (case_id);
