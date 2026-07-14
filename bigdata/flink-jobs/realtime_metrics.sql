-- ============================================================================
-- HFusionData Analytics — 实时聚合:Kafka → 1 分钟窗口 → MySQL/ClickHouse
--
-- 指标面(按 租户 × 模型 × 分钟):请求数、token 总量、成本、平均/最大延迟、
-- 错误步数 —— 供运营大屏实时区与 Java RealtimeThresholdScheduler 阈值监控。
--
-- 精简档:sink 到 MySQL analytics_realtime_metrics(V82 迁移建表);
-- 标准档:追加 ClickHouse sink(见文件末尾注释)。
-- 窗口语义:TUMBLING 1 分钟,按 processing time(事件 created_at 与到达
-- 时刻偏差 < 秒级,演示与运营场景等价)。
-- ============================================================================

INSERT INTO mysql_realtime_metrics
SELECT
    window_start,
    window_end,
    tenant_id,
    model,
    request_count,
    total_tokens,
    total_cost,
    avg_latency_ms,
    max_latency_ms
FROM TABLE(
    TUMBLE(
        TABLE aggregated_stream,
        DESCRIPTOR(row_time),
        INTERVAL '1' MINUTE
    )
);

-- aggregated_stream 定义(00_catalogs.sql 中):
--   CREATE VIEW aggregated_stream AS
--   SELECT
--       TO_TIMESTAMP(created_at)                          AS row_time,
--       CAST(tenant_id AS BIGINT)                         AS tenant_id,
--       model,
--       COUNT(*)                                          AS request_count,
--       SUM(CAST(total_tokens AS BIGINT))                 AS total_tokens,
--       SUM(CAST(cost_usd AS DECIMAL(12, 6)))             AS total_cost,
--       CAST(AVG(CAST(latency_ms AS BIGINT)) AS BIGINT)   AS avg_latency_ms,
--       CAST(MAX(CAST(latency_ms AS BIGINT)) AS BIGINT)   AS max_latency_ms
--   FROM kafka_ods_model_usage_record
--   WHERE tenant_id IS NOT NULL AND tenant_id != ''
--   GROUP BY
--       window(TUMBLE, DESCRIPTOR(row_time), INTERVAL '1' MINUTE),
--       tenant_id, model;

-- ── 标准档附加:同一聚合写 ClickHouse(列存,大屏秒级查询) ────────────────
-- INSERT INTO clickhouse_realtime_metrics
-- SELECT window_start, window_end, tenant_id, model,
--        request_count, total_tokens, total_cost, avg_latency_ms, max_latency_ms
-- FROM TABLE(
--     TUMBLE(TABLE aggregated_stream, DESCRIPTOR(row_time), INTERVAL '1' MINUTE)
-- );
