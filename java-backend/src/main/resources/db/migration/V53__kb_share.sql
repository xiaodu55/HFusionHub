-- C2: 知识库共享（只读协作为主）
CREATE TABLE kb_share (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    knowledge_base_id BIGINT NOT NULL COMMENT 'FK → knowledge_base.id',
    owner_user_id     BIGINT NOT NULL COMMENT '知识库所有者',
    shared_user_id    BIGINT NOT NULL COMMENT '被共享用户',
    permission        VARCHAR(20) NOT NULL DEFAULT 'read' COMMENT 'read | read_write（当前仅 read 生效）',
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted           TINYINT NOT NULL DEFAULT 0,
    UNIQUE KEY uk_kb_share (knowledge_base_id, shared_user_id, deleted),
    INDEX idx_share_user (shared_user_id)
) COMMENT='知识库共享记录';
