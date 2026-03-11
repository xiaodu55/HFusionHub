-- V14: lifecycle controls for user-scoped long-term memory.
ALTER TABLE memory_entry
    ADD COLUMN expires_at DATETIME NULL COMMENT 'Optional memory expiry time';

CREATE INDEX idx_memory_user_expiry ON memory_entry (user_id, expires_at);
CREATE INDEX idx_memory_user_kb ON memory_entry (user_id, knowledge_base_id);
