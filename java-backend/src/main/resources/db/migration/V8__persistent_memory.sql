-- V8: Persistent memory for AI conversations
-- Adds entity-fact, summary, and preference memory with user-scoped access.

CREATE TABLE IF NOT EXISTS memory_entry (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT        NOT NULL,
    type        VARCHAR(32)   NOT NULL DEFAULT 'entity_fact',
    content     TEXT          NOT NULL,
    entities    JSON          NULL     COMMENT 'Extracted entities as JSON array',
    conversation_id BIGINT    NULL     COMMENT 'Nullable: cross-conversation memories have NULL conversation_id',
    knowledge_base_id BIGINT  NULL,
    importance  DOUBLE        NOT NULL DEFAULT 0.5,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_memory_user (user_id),
    INDEX idx_memory_conv (conversation_id),
    INDEX idx_memory_type (type),
    CONSTRAINT fk_memory_user FOREIGN KEY (user_id) REFERENCES sys_user(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- memory_type values:
--   conversation_summary  — compressed summary of a conversation segment
--   entity_fact           — a factual claim about a named entity
--   user_preference       — a stated user preference or instruction
