CREATE TABLE user_model_config (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    provider_type VARCHAR(32) NOT NULL,
    provider_name VARCHAR(100) NOT NULL,
    base_url VARCHAR(500) NOT NULL,
    model_name VARCHAR(160) NOT NULL,
    api_key_ciphertext TEXT NULL,
    enabled TINYINT NOT NULL DEFAULT 1,
    last_test_status VARCHAR(20) NULL,
    last_test_message VARCHAR(500) NULL,
    last_tested_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uk_user_model_config_user UNIQUE (user_id),
    CONSTRAINT fk_user_model_config_user FOREIGN KEY (user_id) REFERENCES sys_user(id) ON DELETE CASCADE
);

