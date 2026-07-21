-- ============================================================================
-- HFusionData Analytics — ClickHouse 初始化(标准档)
-- 挂载为 /docker-entrypoint-initdb.d/,容器首启自动执行。
-- 精简档不部署 ClickHouse:实时指标由 Flink 直写 MySQL analytics_realtime_metrics,
-- 大屏与告警链路完全一致,仅失去列存加速(演示/小客户无感)。
-- ============================================================================

CREATE DATABASE IF NOT EXISTS analytics;

-- ── 实时指标(Flink JDBC sink 直接 upsert;主键去重,ReplacingMergeTree 兜底) ──
CREATE TABLE IF NOT EXISTS analytics.realtime_metrics
(
    window_start   DateTime          COMMENT '窗口开始(UTC)',
    window_end     DateTime,
    tenant_id      Int64,
    model          String,
    request_count  UInt64,
    total_tokens   UInt64,
    total_cost     Decimal(12, 6),
    avg_latency_ms UInt64,
    max_latency_ms UInt64,
    version        UInt64 MATERIALIZED toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(version)
PARTITION BY toYYYYMM(window_start)
ORDER BY (window_start, tenant_id, model);

-- ── 租户 × 模型 × 日聚合镜像(由 ch_sync.py 从 HDFS DWS 层同步;供大屏高频
--    查询降载与 OLAP 对比实验)。注意:ReplacingMergeTree 的 version 列必须
--    在建表时内联声明——曾放在 CREATE 之后的 ALTER 里补,首启校验即报
--    "Version column version does not exist"(NO_SUCH_COLUMN_IN_TABLE)。
CREATE TABLE IF NOT EXISTS analytics.ads_tenant_model_daily
(
    stat_date         Date,
    tenant_id         Int64,
    model             String,
    call_count        UInt64,
    prompt_tokens     UInt64,
    completion_tokens UInt64,
    total_tokens      UInt64,
    cost_usd          Decimal(12, 6),
    avg_latency_ms    UInt64,
    p95_latency_ms    UInt64,
    version           UInt64 MATERIALIZED toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(version)
PARTITION BY toYYYYMM(stat_date)
ORDER BY (stat_date, tenant_id, model)
;

-- ── 大屏常用查询(物化视图:按天预聚合请求量与成本速率) ─────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_realtime_per_min
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(minute)
ORDER BY (minute, tenant_id)
AS SELECT
    toStartOfMinute(window_start) AS minute,
    tenant_id,
    sum(request_count)            AS request_count,
    sum(total_tokens)             AS total_tokens,
    sum(total_cost)               AS total_cost
FROM analytics.realtime_metrics
GROUP BY minute, tenant_id;

-- ── DWD 明细镜像(由 ch_sync.py 从 HDFS Parquet 同步;OLAP 加速对比实验用) ──
CREATE TABLE IF NOT EXISTS analytics.dwd_llm_call
(
    dt                LowCardinality(String),
    tenant_id         Int64,
    user_id           Nullable(Int64),
    conversation_id   Nullable(Int64),
    agent_task_id     Nullable(Int64),
    model             LowCardinality(String),
    provider          LowCardinality(String),
    request_type      LowCardinality(String),
    prompt_tokens     Nullable(Int64),
    completion_tokens Nullable(Int64),
    total_tokens      Nullable(Int64),
    cost_usd          Nullable(Decimal(12, 6)),
    latency_ms        Nullable(Int64),
    created_at        DateTime,
    event_date        Date,
    version           UInt64 MATERIALIZED toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(version)
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_date, tenant_id, model, created_at);
