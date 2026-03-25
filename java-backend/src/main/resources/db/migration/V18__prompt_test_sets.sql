-- Prompt Test Set — save fixed questions + variable values, batch-run against any template.

CREATE TABLE IF NOT EXISTS prompt_test_set (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uk_pts_user_name UNIQUE (user_id, name),
    CONSTRAINT fk_pts_user FOREIGN KEY (user_id) REFERENCES sys_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_pts_user_updated ON prompt_test_set (user_id, updated_at);

CREATE TABLE IF NOT EXISTS prompt_test_case (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    set_id BIGINT NOT NULL,
    question VARCHAR(4000) NOT NULL,
    variables TEXT DEFAULT NULL COMMENT 'Template variable values as JSON, e.g. {"role":"客服","topic":"退款"}',
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ptc_set FOREIGN KEY (set_id) REFERENCES prompt_test_set(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ptc_set_order ON prompt_test_case (set_id, sort_order);
