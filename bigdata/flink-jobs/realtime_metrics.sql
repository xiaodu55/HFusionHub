-- ============================================================================
-- HFusionData Analytics — 实时聚合:Kafka → 1 分钟 TVF 窗口 → MySQL
-- 提交: sql-client.sh -f realtime_metrics.sql(表定义在 00_catalogs.sql,
--       合并提交方式见 README §2)
-- 指标面(租户 × 模型 × 分钟):请求数/token/成本/平均与最大延迟。
-- 精简档 sink 到 MySQL analytics_realtime_metrics;标准档可加 ClickHouse sink。
-- ============================================================================

INSERT INTO mysql_realtime_metrics
SELECT
    window_start,
    window_end,
    tenant_id,
    model,
    COUNT(*)                              AS request_count,
    SUM(total_tokens)                     AS total_tokens,
    SUM(cost_usd)                         AS total_cost,
    CAST(AVG(latency_ms) AS BIGINT)       AS avg_latency_ms,
    CAST(MAX(latency_ms) AS BIGINT)       AS max_latency_ms
FROM TABLE(
    TUMBLE(
        TABLE aggregated_stream,
        DESCRIPTOR(row_time),
        INTERVAL '1' MINUTE
    )
)
GROUP BY window_start, window_end, tenant_id, model;
