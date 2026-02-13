-- Apply once to existing HFusionHub databases before deploying the durable RAG index job flow.

CREATE TABLE IF NOT EXISTS `document_index_job` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '索引任务ID',
    `document_id` BIGINT NOT NULL COMMENT '文档ID',
    `knowledge_base_id` BIGINT NOT NULL COMMENT '知识库ID',
    `index_version` VARCHAR(64) NOT NULL COMMENT '本次索引版本/回调幂等键',
    `embedding_model` VARCHAR(100) DEFAULT NULL COMMENT '嵌入模型',
    `status` VARCHAR(20) NOT NULL COMMENT 'PENDING/PROCESSING/COMPLETED/FAILED/SUPERSEDED',
    `attempt` INT NOT NULL DEFAULT 1 COMMENT '该文档的第几次索引尝试',
    `chunk_count` INT NOT NULL DEFAULT 0 COMMENT '成功写入的分块数',
    `error_message` VARCHAR(1000) DEFAULT NULL COMMENT '失败原因',
    `started_at` DATETIME DEFAULT NULL COMMENT '开始时间',
    `completed_at` DATETIME DEFAULT NULL COMMENT '结束时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `deleted` TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_document_index_version` (`document_id`, `index_version`),
    KEY `idx_document_job_status` (`document_id`, `status`),
    KEY `idx_job_status_created` (`status`, `created_at`),
    CONSTRAINT `fk_index_job_document` FOREIGN KEY (`document_id`) REFERENCES `document` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档索引任务';

CREATE TABLE IF NOT EXISTS `document_chunk` (
    `chunk_id` VARCHAR(128) NOT NULL COMMENT '分块稳定ID',
    `document_id` BIGINT NOT NULL COMMENT '文档ID',
    `knowledge_base_id` BIGINT NOT NULL COMMENT '知识库ID',
    `index_version` VARCHAR(64) NOT NULL COMMENT '产生该元数据的索引版本',
    `chunk_index` INT NOT NULL COMMENT '文档内顺序',
    `block_type` VARCHAR(32) DEFAULT NULL COMMENT '块类型',
    `outline_path` JSON DEFAULT NULL COMMENT '章节路径',
    `content_excerpt` VARCHAR(1000) DEFAULT NULL COMMENT '用于引用展示的摘要',
    `char_count` INT DEFAULT NULL COMMENT '原始文本长度',
    `metadata` JSON DEFAULT NULL COMMENT '解析器元数据',
    PRIMARY KEY (`chunk_id`),
    KEY `idx_chunk_document_version` (`document_id`, `index_version`),
    KEY `idx_chunk_kb_document` (`knowledge_base_id`, `document_id`),
    CONSTRAINT `fk_chunk_document` FOREIGN KEY (`document_id`) REFERENCES `document` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档分块元数据';
