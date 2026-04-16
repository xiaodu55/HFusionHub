ALTER TABLE user_model_config
    ADD COLUMN tenant_id BIGINT NOT NULL DEFAULT 1 AFTER user_id,
    ADD KEY idx_user_model_config_user_fk (user_id);

ALTER TABLE user_model_config
    DROP INDEX uk_user_model_config_user;

ALTER TABLE user_model_config
    ADD CONSTRAINT uk_user_model_config_tenant_user UNIQUE (tenant_id, user_id),
    ADD KEY idx_user_model_config_tenant (tenant_id, enabled);
