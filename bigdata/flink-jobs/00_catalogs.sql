-- ============================================================================
-- HFusionData Analytics — Flink SQL 公共 catalog 定义(source/sink/视图)
--
-- 用 sql-client 的 -i 参数在每个作业前预载:
--   sql-client.sh -i 00_catalogs.sql -f <作业>.sql
-- 依赖 connector jar 见 README.md 第 1 节。
-- ============================================================================

-- ── Kafka source:各 ODS topic(JSON,值结构与 cdc_ingest.sql 的 INSERT 对齐) ──
CREATE TABLE kafka_ods_model_usage_record (
    user_id           STRING,
    tenant_id         STRING,
    conversation_id   STRING,
    agent_task_id     STRING,
    model             STRING,
    provider          STRING,
    prompt_tokens     BIGINT,
    completion_tokens BIGINT,
    total_tokens      BIGINT,
    cost_usd          STRING,
    latency_ms        BIGINT,
    request_type      STRING,
    created_at        STRING,
    dt                STRING,
    row_time AS TO_TIMESTAMP(created_at),
    WATERMARK FOR row_time AS row_time - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'ods_model_usage_record',
    'properties.bootstrap.servers' = 'analytics-kafka:9092',
    'properties.group.id' = 'flink_analytics',
    'scan.startup.mode' = 'group-offsets',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

CREATE TABLE kafka_ods_agent_step (
    run_id       STRING,
    sequence     STRING,
    step_type    STRING,
    action       STRING,
    duration_ms  BIGINT,
    error_code   STRING,
    created_at   STRING,
    dt           STRING
) WITH (
    'connector' = 'kafka',
    'topic' = 'ods_agent_step',
    'properties.bootstrap.servers' = 'analytics-kafka:9092',
    'properties.group.id' = 'flink_analytics',
    'scan.startup.mode' = 'group-offsets',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

CREATE TABLE kafka_ods_usage_event (
    tenant_id   STRING,
    meter       STRING,
    operation   STRING,
    request_id  STRING,
    window_key  STRING,
    amount      STRING,
    ref_type    STRING,
    ref_id      STRING,
    created_at  STRING,
    dt          STRING
) WITH (
    'connector' = 'kafka',
    'topic' = 'ods_usage_event',
    'properties.bootstrap.servers' = 'analytics-kafka:9092',
    'properties.group.id' = 'flink_analytics',
    'scan.startup.mode' = 'group-offsets',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

CREATE TABLE kafka_ods_agent_task (
    request_id        STRING,
    user_id           STRING,
    conversation_id   STRING,
    knowledge_base_id STRING,
    status            STRING,
    current_run_id    STRING,
    created_at        STRING,
    dt                STRING
) WITH (
    'connector' = 'kafka',
    'topic' = 'ods_agent_task',
    'properties.bootstrap.servers' = 'analytics-kafka:9092',
    'properties.group.id' = 'flink_analytics',
    'scan.startup.mode' = 'group-offsets',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

-- ── HDFS filesystem sink:与 full_import.py 写同一 ODS 路径(全量+增量合流) ──
CREATE TABLE hdfs_ods_model_usage_record (
    user_id           STRING,
    tenant_id         STRING,
    conversation_id   STRING,
    agent_task_id     STRING,
    model             STRING,
    provider          STRING,
    prompt_tokens     BIGINT,
    completion_tokens BIGINT,
    total_tokens      BIGINT,
    cost_usd          STRING,
    latency_ms        BIGINT,
    request_type      STRING,
    created_at        STRING,
    dt                STRING
) PARTITIONED BY (dt) WITH (
    'connector' = 'filesystem',
    'path' = 'hdfs://hadoop-namenode:9000/warehouse/hfusionhub/ods/model_usage_record',
    'format' = 'parquet',
    'sink.rolling-policy.rollover-interval' = '15min',
    'sink.rolling-policy.check-interval' = '1min',
    'sink.partition-commit.policy.kind' = 'success-file',
    'sink.partition-commit.delay' = '1min'
);

CREATE TABLE hdfs_ods_agent_step (
    run_id       STRING,
    sequence     STRING,
    step_type    STRING,
    action       STRING,
    duration_ms  BIGINT,
    error_code   STRING,
    created_at   STRING,
    dt           STRING
) PARTITIONED BY (dt) WITH (
    'connector' = 'filesystem',
    'path' = 'hdfs://hadoop-namenode:9000/warehouse/hfusionhub/ods/agent_step',
    'format' = 'parquet',
    'sink.rolling-policy.rollover-interval' = '15min',
    'sink.rolling-policy.check-interval' = '1min',
    'sink.partition-commit.policy.kind' = 'success-file',
    'sink.partition-commit.delay' = '1min'
);

CREATE TABLE hdfs_ods_usage_event (
    tenant_id   STRING,
    meter       STRING,
    operation   STRING,
    request_id  STRING,
    window_key  STRING,
    amount      STRING,
    ref_type    STRING,
    ref_id      STRING,
    created_at  STRING,
    dt          STRING
) PARTITIONED BY (dt) WITH (
    'connector' = 'filesystem',
    'path' = 'hdfs://hadoop-namenode:9000/warehouse/hfusionhub/ods/usage_event',
    'format' = 'parquet',
    'sink.rolling-policy.rollover-interval' = '15min',
    'sink.rolling-policy.check-interval' = '1min',
    'sink.partition-commit.policy.kind' = 'success-file',
    'sink.partition-commit.delay' = '1min'
);

CREATE TABLE hdfs_ods_agent_task (
    request_id        STRING,
    user_id           STRING,
    conversation_id   STRING,
    knowledge_base_id STRING,
    status            STRING,
    current_run_id    STRING,
    created_at        STRING,
    dt                STRING
) PARTITIONED BY (dt) WITH (
    'connector' = 'filesystem',
    'path' = 'hdfs://hadoop-namenode:9000/warehouse/hfusionhub/ods/agent_task',
    'format' = 'parquet',
    'sink.rolling-policy.rollover-interval' = '15min',
    'sink.rolling-policy.check-interval' = '1min',
    'sink.partition-commit.policy.kind' = 'success-file',
    'sink.partition-commit.delay' = '1min'
);

-- ── MySQL JDBC sink:实时指标(精简档主 sink,V82 迁移建表) ─────────────────
CREATE TABLE mysql_realtime_metrics (
    window_start    TIMESTAMP(3),
    window_end      TIMESTAMP(3),
    tenant_id       BIGINT,
    model           STRING,
    request_count   BIGINT,
    total_tokens    BIGINT,
    total_cost      DECIMAL(12, 6),
    avg_latency_ms  BIGINT,
    max_latency_ms  BIGINT,
    PRIMARY KEY (window_start, tenant_id, model) NOT ENFORCED
) WITH (
    'connector' = 'jdbc',
    'url' = 'jdbc:mysql://mysql8:3306/hfusionhub?useSSL=false&allowPublicKeyRetrieval=true',
    'table-name' = 'analytics_realtime_metrics',
    'username' = 'hfusion',
    'password' = 'CHANGE_ME',      -- 与 cdc_ingest.sql 统一由部署注入
    'sink.buffer-flush.max-rows' = '200',
    'sink.buffer-flush.interval' = '5s'
);

-- ── 聚合视图:租户 × 模型 维度(供 realtime_metrics.sql 窗口消费) ──────────
CREATE TEMPORARY VIEW aggregated_stream AS
SELECT
    row_time                                          AS row_time,
    CAST(tenant_id AS BIGINT)                         AS tenant_id,
    model,
    COUNT(*)                                          AS request_count,
    SUM(total_tokens)                                 AS total_tokens,
    SUM(CAST(cost_usd AS DECIMAL(12, 6)))             AS total_cost,
    CAST(AVG(latency_ms) AS BIGINT)                   AS avg_latency_ms,
    CAST(MAX(latency_ms) AS BIGINT)                   AS max_latency_ms
FROM kafka_ods_model_usage_record
WHERE tenant_id IS NOT NULL AND tenant_id <> ''
GROUP BY
    window(TUMBLE, DESCRIPTOR(row_time), INTERVAL '1' MINUTE),
    tenant_id,
    model;

-- ── 标准档可选:ClickHouse sink(开启需先启用 jdbc-clickhouse connector) ───
-- CREATE TABLE clickhouse_realtime_metrics (
--     window_start   TIMESTAMP(3),
--     window_end     TIMESTAMP(3),
--     tenant_id      BIGINT,
--     model          STRING,
--     request_count  BIGINT,
--     total_tokens   BIGINT,
--     total_cost     DECIMAL(12, 6),
--     avg_latency_ms BIGINT,
--     max_latency_ms BIGINT
-- ) WITH (
--     'connector' = 'jdbc',
--     'url' = 'jdbc:clickhouse://analytics-clickhouse:8123/analytics',
--     'table-name' = 'realtime_metrics',
--     'username' = 'analytics',
--     'password' = 'CHANGE_ME'
-- );
