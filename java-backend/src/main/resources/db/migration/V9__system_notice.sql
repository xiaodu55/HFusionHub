-- V9: System notices and notification recipients

CREATE TABLE IF NOT EXISTS system_notice (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    title       VARCHAR(256)  NOT NULL,
    content     TEXT          NOT NULL,
    level       VARCHAR(16)   NOT NULL DEFAULT 'info',
    publisher   VARCHAR(64)   NULL     COMMENT 'admin username',
    scope       VARCHAR(32)   NOT NULL DEFAULT 'all',
    expires_at  DATETIME      NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_notice_created (created_at DESC),
    INDEX idx_notice_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- level: info | warning | error
-- scope: all | admin | user

CREATE TABLE IF NOT EXISTS notice_recipient (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    notice_id   BIGINT        NOT NULL,
    user_id     BIGINT        NOT NULL,
    is_read     TINYINT(1)    NOT NULL DEFAULT 0,
    read_at     DATETIME      NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_notice_user (notice_id, user_id),
    INDEX idx_recipient_user_unread (user_id, is_read),
    CONSTRAINT fk_recipient_notice FOREIGN KEY (notice_id) REFERENCES system_notice(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
