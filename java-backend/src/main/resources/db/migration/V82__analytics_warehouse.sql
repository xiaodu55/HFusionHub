-- V82: HFusionData Analytics — 运营数仓应用层
-- 三类表:
--   analytics_realtime_metrics  Flink 实时聚合落点(1 分钟窗口,租户x模型)
--   ads_*                       Spark ADS 结果的 MySQL 同构镜像(业务侧消费)
--   bigdata_batch_run_log       批处理调度/回补执行日志
-- 全部含 tenant_id(平台全局口径统一用 -1 表示);详细语义见
-- docs/BIGDATA_ARCHITECTURE.md 第 4 节数据字典。

CREATE TABLE IF NOT EXISTS analytics_realtime_metrics (
    id            BIGINT       NOT NULL AUTO_INCREMENT,
    window_start  DATETIME     NOT NULL COMMENT '窗口开始(UTC)',
    window_end    DATETIME     NOT NULL,
    tenant_id     BIGINT       NOT NULL,
    model         VARCHAR(100) NOT NULL,
    request_count BIGINT       NOT NULL DEFAULT 0,
    total_tokens  BIGINT       NOT NULL DEFAULT 0,
    total_cost    DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    avg_latency_ms BIGINT      NOT NULL DEFAULT 0,
    max_latency_ms BIGINT      NOT NULL DEFAULT 0,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_rt_window (window_start, tenant_id, model),
    KEY idx_rt_window_start (window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='实时聚合指标(1min 窗口)';

CREATE TABLE IF NOT EXISTS ads_cost_daily (
    id             BIGINT        NOT NULL AUTO_INCREMENT,
    tenant_id      BIGINT        NOT NULL COMMENT '租户ID,-1=平台全局',
    stat_date      DATE          NOT NULL,
    call_count     BIGINT        NOT NULL DEFAULT 0,
    total_tokens   BIGINT        NOT NULL DEFAULT 0,
    cost_usd       DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    est_month_cost DECIMAL(12,2) DEFAULT NULL COMMENT '线性外推月费(租户口径)',
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ads_cost (tenant_id, stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每日成本趋势(ADS 镜像)';

CREATE TABLE IF NOT EXISTS ads_model_share (
    id         BIGINT        NOT NULL AUTO_INCREMENT,
    tenant_id  BIGINT        NOT NULL,
    model      VARCHAR(100)  NOT NULL,
    stat_date  DATE          NOT NULL,
    call_count BIGINT        NOT NULL DEFAULT 0,
    cost_usd   DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    cost_share DOUBLE        NOT NULL DEFAULT 0 COMMENT '当日成本占比 0-1',
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ads_model (tenant_id, model, stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型成本占比(ADS 镜像)';

CREATE TABLE IF NOT EXISTS ads_tenant_topn (
    id           BIGINT        NOT NULL AUTO_INCREMENT,
    stat_date    DATE          NOT NULL,
    rank_no      INT           NOT NULL COMMENT '当日成本排名(1-based)',
    tenant_id    BIGINT        NOT NULL,
    call_count   BIGINT        NOT NULL DEFAULT 0,
    total_tokens BIGINT        NOT NULL DEFAULT 0,
    cost_usd     DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ads_topn (stat_date, rank_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户用量 TopN(平台管理员视图)';

CREATE TABLE IF NOT EXISTS ads_tool_success (
    id           BIGINT   NOT NULL AUTO_INCREMENT,
    tenant_id    BIGINT   NOT NULL,
    step_type    VARCHAR(50) NOT NULL,
    stat_date    DATE     NOT NULL,
    step_count   BIGINT   NOT NULL DEFAULT 0,
    error_count  BIGINT   NOT NULL DEFAULT 0,
    success_rate DOUBLE   NOT NULL DEFAULT 1,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ads_tool (tenant_id, step_type, stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent 步骤成功率(ADS 镜像)';

CREATE TABLE IF NOT EXISTS ads_eval_quality (
    id             BIGINT   NOT NULL AUTO_INCREMENT,
    tenant_id      BIGINT   NOT NULL COMMENT '评测 run 归属租户,-1=平台跑批',
    stat_date      DATE     NOT NULL,
    eval_count     BIGINT   NOT NULL DEFAULT 0,
    avg_hit_ratio  DOUBLE   DEFAULT NULL COMMENT '期望文档平均命中率',
    avg_ttft_ms    BIGINT   DEFAULT NULL,
    avg_latency_ms BIGINT   DEFAULT NULL,
    failure_rate   DOUBLE   NOT NULL DEFAULT 0,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ads_eval (tenant_id, stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='检索/评测质量趋势(ADS 镜像)';

CREATE TABLE IF NOT EXISTS bigdata_batch_run_log (
    id           BIGINT        NOT NULL AUTO_INCREMENT,
    tenant_id    BIGINT        DEFAULT NULL COMMENT '触发者租户(手工回补记录;日终调度为 NULL)',
    job_name     VARCHAR(50)   NOT NULL COMMENT 'full-import|dwd-transform|dws-aggregate|quality-check|ads-build|pipeline',
    batch_date   DATE          NOT NULL COMMENT '处理的数据日期(dt)',
    command      VARCHAR(1000) DEFAULT NULL COMMENT '执行命令(脱敏后)',
    status       VARCHAR(20)   NOT NULL DEFAULT 'RUNNING' COMMENT 'RUNNING|SUCCESS|FAILED|SKIPPED',
    exit_code    INT           DEFAULT NULL,
    started_at   DATETIME      NOT NULL,
    finished_at  DATETIME      DEFAULT NULL,
    duration_ms  BIGINT        DEFAULT NULL,
    log_excerpt  VARCHAR(2000) DEFAULT NULL COMMENT 'stdout/stderr 尾部(排障用)',
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_batch_date (batch_date, job_name),
    KEY idx_batch_status (status, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='大数据批处理执行日志';
