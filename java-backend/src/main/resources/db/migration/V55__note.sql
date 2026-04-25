-- User notes (写笔记闭环): persisted by Java from Agent write_note tool callbacks
-- and by the user-facing note management API.
CREATE TABLE `note` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '笔记ID',
    `user_id` BIGINT NOT NULL COMMENT '所属用户ID',
    `tenant_id` BIGINT NULL COMMENT '所属租户ID',
    `knowledge_base_id` BIGINT NULL COMMENT '关联知识库ID（可空）',
    `conversation_id` BIGINT NULL COMMENT '来源会话ID（可空）',
    `message_id` BIGINT NULL COMMENT '来源消息ID（可空）',
    `title` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '笔记标题',
    `content` TEXT NOT NULL COMMENT '笔记内容（Markdown）',
    `source` VARCHAR(32) NOT NULL DEFAULT 'manual' COMMENT '来源: manual|agent_write_note',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除: 0-未删除 1-已删除',
    PRIMARY KEY (`id`),
    KEY `idx_note_user` (`user_id`, `deleted`, `created_at`),
    KEY `idx_note_kb` (`knowledge_base_id`, `deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户笔记';
