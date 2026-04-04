-- HFusionHub V35 — 租户用量账本与配额
-- 里程碑 1: 账本核心 + 聊天入口限额。
-- 四张表:
--   1. usage_event      不可变追加账本；唯一键 (tenant_id, meter, request_id, operation)
--                      保证同一 (租户, 计量项, 业务请求, 操作) 各只落账一次（幂等）。
--   2. usage_reservation 显式预占状态机；每 (tenant_id, meter, request_id) 一行，
--                       自 RESERVED 原子转换到 COMMITTED 或 RELEASED 之一，杜绝
--                       COMMIT 后再 RELEASE / RELEASE 后再 COMMIT 导致的 reserved 扣负。
--   3. usage_counter    每个 (tenant, meter, day) 的原子计数器；reserve/settle 走
--                       条件 UPDATE，避免应用层竞态。
--   4. tenant_quota     租户级配额覆盖（不填则回落 plan_tier 默认值）。
--
-- 结算/退回一律使用对应预占（usage_reservation）的 window_key，防止跨 UTC 零点时
-- 在新一天扣减预留、旧一天遗留 reserved。四表均带 tenant_id，由租户行拦截器隔离。

CREATE TABLE IF NOT EXISTS usage_event (
    id          BIGINT      NOT NULL AUTO_INCREMENT,
    tenant_id   BIGINT      NOT NULL COMMENT '租户 ID',
    meter       VARCHAR(32) NOT NULL COMMENT '计量项: chat_tokens|agent_tokens|index_chunks|plugin_executions',
    operation   VARCHAR(16) NOT NULL COMMENT '账本操作: RESERVE|COMMIT|RELEASE',
    request_id  VARCHAR(64) NOT NULL COMMENT '业务幂等键（聊天/索引/运行/插件执行的请求 ID）',
    window_key  VARCHAR(10) NOT NULL COMMENT 'UTC 日窗口 YYYY-MM-DD（取自对应预占）',
    amount      BIGINT      NOT NULL DEFAULT 0 COMMENT 'RESERVE=预占上界, COMMIT=实际结算量, RELEASE=退回量',
    ref_type    VARCHAR(32) DEFAULT NULL COMMENT '引用类型: message|document_index|agent_run|plugin_execution',
    ref_id      VARCHAR(64) DEFAULT NULL COMMENT '引用 ID',
    created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_usage_request_op (tenant_id, meter, request_id, operation),
    KEY idx_usage_reservation (tenant_id, meter, request_id),
    KEY idx_usage_tenant_window (tenant_id, window_key),
    KEY idx_usage_meter_window (meter, window_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用量账本（不可变）';

CREATE TABLE IF NOT EXISTS usage_reservation (
    id              BIGINT      NOT NULL AUTO_INCREMENT,
    tenant_id       BIGINT      NOT NULL COMMENT '租户 ID',
    meter           VARCHAR(32) NOT NULL COMMENT '计量项',
    request_id      VARCHAR(64) NOT NULL COMMENT '业务幂等键',
    window_key      VARCHAR(10) NOT NULL COMMENT '预占所在 UTC 日窗口 YYYY-MM-DD',
    reserved_amount BIGINT      NOT NULL COMMENT '预占上界（输入估算 + 服务端最大输出）',
    actual_amount   BIGINT      NOT NULL DEFAULT 0 COMMENT '实际结算量（COMMIT 时写入）',
    state           VARCHAR(16) NOT NULL DEFAULT 'RESERVED' COMMENT '状态机: RESERVED|COMMITTED|RELEASED',
    ref_type        VARCHAR(32) DEFAULT NULL COMMENT '引用类型',
    ref_id          VARCHAR(64) DEFAULT NULL COMMENT '引用 ID',
    created_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_reservation (tenant_id, meter, request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用量预占状态机';

CREATE TABLE IF NOT EXISTS usage_counter (
    id          BIGINT      NOT NULL AUTO_INCREMENT,
    tenant_id   BIGINT      NOT NULL COMMENT '租户 ID',
    meter       VARCHAR(32) NOT NULL COMMENT '计量项',
    window_key  VARCHAR(10) NOT NULL COMMENT 'UTC 日窗口 YYYY-MM-DD',
    reserved    BIGINT      NOT NULL DEFAULT 0 COMMENT '当日已预占未结算量',
    committed   BIGINT      NOT NULL DEFAULT 0 COMMENT '当日已结算（实际消耗）量',
    created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_counter (tenant_id, meter, window_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日用量计数器';

CREATE TABLE IF NOT EXISTS tenant_quota (
    id          BIGINT      NOT NULL AUTO_INCREMENT,
    tenant_id   BIGINT      NOT NULL COMMENT '租户 ID',
    meter       VARCHAR(32) NOT NULL COMMENT '计量项',
    daily_limit BIGINT      NOT NULL COMMENT '日限额覆盖值（>=0）',
    created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_tenant_meter (tenant_id, meter)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户配额覆盖';