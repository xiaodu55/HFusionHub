-- V16: user-owned prompt templates and optional conversation binding.
CREATE TABLE IF NOT EXISTS prompt_template (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    content TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    version INT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uk_prompt_template_user_name UNIQUE (user_id, name),
    CONSTRAINT fk_prompt_template_user FOREIGN KEY (user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_prompt_template_user_status ON prompt_template (user_id, status, updated_at);

ALTER TABLE conversation
    ADD COLUMN prompt_template_id BIGINT NULL COMMENT 'Published prompt template selected for this conversation';

CREATE INDEX idx_conversation_prompt_template ON conversation (prompt_template_id);
