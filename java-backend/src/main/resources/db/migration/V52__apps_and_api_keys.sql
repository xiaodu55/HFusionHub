-- B1/C4: 对外发布应用（App）与 API Key
-- 应用将「知识库 + 模型 + 回答风格」打包为可对外调用的 Agent 端点；
-- API Key 哈希存储，调用计入 app_call_log（按 Key 计费）。

CREATE TABLE app (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(200) NOT NULL COMMENT '应用名称',
    description         VARCHAR(500) DEFAULT NULL COMMENT '应用描述',
    user_id             BIGINT NOT NULL COMMENT '所有者（sys_user.id）',
    tenant_id           BIGINT NOT NULL DEFAULT 1 COMMENT '租户',
    knowledge_base_id   BIGINT DEFAULT NULL COMMENT '绑定知识库（空=通用对话）',
    prompt_template_id  BIGINT DEFAULT NULL COMMENT '可选提示词模板',
    model               VARCHAR(200) DEFAULT NULL COMMENT '模型覆盖（空=系统默认）',
    style               VARCHAR(20) NOT NULL DEFAULT 'detailed' COMMENT 'concise | detailed | report',
    status              TINYINT NOT NULL DEFAULT 0 COMMENT '0 草稿, 1 已发布, 2 已停用',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted             TINYINT NOT NULL DEFAULT 0,
    INDEX idx_app_user (user_id),
    INDEX idx_app_tenant (tenant_id)
) COMMENT='对外发布的应用/Agent';

CREATE TABLE app_api_key (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    app_id      BIGINT NOT NULL COMMENT 'FK → app.id',
    name        VARCHAR(100) DEFAULT NULL COMMENT 'Key 名称（便于识别）',
    key_hash    VARCHAR(64) NOT NULL COMMENT '密钥 SHA-256 hex（不存明文）',
    key_prefix  VARCHAR(12) NOT NULL COMMENT '明文前缀前 8 位，用于展示',
    enabled     TINYINT NOT NULL DEFAULT 1 COMMENT '1 启用, 0 停用',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted     TINYINT NOT NULL DEFAULT 0,
    INDEX idx_apikey_app (app_id),
    INDEX idx_apikey_hash (key_hash)
) COMMENT='应用 API Key（哈希存储）';

CREATE TABLE app_call_log (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    app_id             BIGINT NOT NULL COMMENT 'FK → app.id',
    api_key_id         BIGINT DEFAULT NULL COMMENT 'FK → app_api_key.id（按 Key 计费）',
    user_id            BIGINT DEFAULT NULL COMMENT '调用方用户（内部调用时）',
    tenant_id          BIGINT NOT NULL DEFAULT 1,
    status             VARCHAR(20) NOT NULL DEFAULT 'ok' COMMENT 'ok | error | rate_limited',
    prompt_tokens      INT NOT NULL DEFAULT 0,
    completion_tokens  INT NOT NULL DEFAULT 0,
    total_tokens       INT NOT NULL DEFAULT 0,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_call_app (app_id, created_at),
    INDEX idx_call_key (api_key_id)
) COMMENT='应用调用记录（含按 Key 计费）';
