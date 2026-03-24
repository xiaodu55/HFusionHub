-- V17: prompt template version history & rollback audit trail.
-- Each create / edit / publish / unpublish / rollback writes a snapshot
-- so every change is traceable and reversible.
CREATE TABLE IF NOT EXISTS prompt_template_version (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    template_id BIGINT NOT NULL,
    version INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    content TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    operation VARCHAR(20) NOT NULL COMMENT 'CREATE | EDIT | PUBLISH | UNPUBLISH | ROLLBACK',
    operator_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ptv_template FOREIGN KEY (template_id) REFERENCES prompt_template(id) ON DELETE CASCADE,
    CONSTRAINT fk_ptv_operator FOREIGN KEY (operator_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ptv_template_version ON prompt_template_version (template_id, version DESC);
