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

-- ── 租户 × 模型 × 日 ADS 镜像(可选:由 clickhouse-jdbc 从 Hive 同步;标准档
--    Superset 直查 Hive,此表供大屏高频查询降载) ─────────────────────────────
CREATE TABLE IF NOT EXISTS analytics.ads_tenant_model_daily
(
    stat_date         Date,
    tenant_id         Int64,
    model             String,
    call_count        UInt64,
    total_tokens      UInt64,
    cost_usd          Decimal(12, 6),
    avg_latency_ms    UInt64,
    p95_latency_ms    UInt64
)
ENGINE = ReplacingMergeTree(version)
PARTITION BY toYYYYMM(stat_date)
ORDER BY (stat_date, tenant_id, model)
;
ALTER TABLE analytics.ads_tenant_model_daily ADD COLUMN IF NOT EXISTS version UInt64 MATERIALIZED toUnixTimestamp(now());

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
