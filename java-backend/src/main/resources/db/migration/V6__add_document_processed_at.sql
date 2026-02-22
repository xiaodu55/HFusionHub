-- V6: Add processed_at column to document table
-- The Document entity has a processedAt field that is set during vectorization callbacks
-- but the column was missing from the original V1 migration.
ALTER TABLE document ADD COLUMN processed_at DATETIME NULL COMMENT '处理完成时间' AFTER error_message;
