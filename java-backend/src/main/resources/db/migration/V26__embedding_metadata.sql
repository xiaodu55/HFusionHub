-- V26: Embedding metadata for vector store migration and reconciliation.
-- Adds embedding_model, embedding_dimension, and embedding_version to
-- document_chunk (for per-chunk provenance) and document_index_job
-- (for per-job provenance).

ALTER TABLE `document_chunk`
    ADD COLUMN `embedding_model` VARCHAR(100) DEFAULT NULL COMMENT '嵌入模型名称' AFTER `metadata`,
    ADD COLUMN `embedding_dimension` INT DEFAULT NULL COMMENT '嵌入向量维度' AFTER `embedding_model`,
    ADD COLUMN `embedding_version` VARCHAR(64) DEFAULT NULL COMMENT '嵌入版本标识' AFTER `embedding_dimension`;

ALTER TABLE `document_index_job`
    ADD COLUMN `embedding_dimension` INT DEFAULT NULL COMMENT '嵌入向量维度' AFTER `embedding_model`,
    ADD COLUMN `embedding_version` VARCHAR(64) DEFAULT NULL COMMENT '嵌入版本标识' AFTER `embedding_dimension`;

-- Backfill existing completed jobs/chunks with defaults for consistency.
UPDATE `document_chunk` SET `embedding_model` = 'unknown' WHERE `embedding_model` IS NULL;
UPDATE `document_index_job` SET `embedding_model` = 'unknown' WHERE `embedding_model` IS NULL AND `status` = 'COMPLETED';
