-- ============================================================================
-- HFusionData Analytics — Flink SQL 公共 catalog 定义
--
-- 结构说明:
--   * upsert_ods_*      — upsert-kafka SINK(CDC 采集写入;PK 去重)
--   * realtime_*        — plain kafka SOURCE(实时指标读取;读到最新值流)
--   * mysql_realtime_metrics — JDBC sink(V82 建表)
--   * aggregated_stream — mur 实时源的透传视图(带 watermark)
-- 提交: sql-client.sh -f <作业>.sql(依赖 connector 见 README.md §1)
-- ============================================================================

-- ── upsert-kafka sinks:CDC 采集写入(JSON key/value,按 id 去重) ───────────
CREATE TABLE upsert_ods_model_usage_record (
    id                BIGINT,
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
    PRIMARY KEY (id) NOT ENFORCED
) WITH (
    'connector' = 'upsert-kafka',
    'topic' = 'ods_model_usage_record',
    'properties.bootstrap.servers' = 'analytics-kafka:9092',
    'key.format' = 'json',
    'value.format' = 'json'
);

CREATE TABLE upsert_ods_agent_step (
    id          BIGINT,
    run_id      STRING,
    sequence    STRING,
    step_type   STRING,
    action      STRING,
    duration_ms BIGINT,
    error_code  STRING,
    created_at  STRING,
    dt          STRING,
    PRIMARY KEY (id) NOT ENFORCED
) WITH (
    'connector' = 'upsert-kafka',
    'topic' = 'ods_agent_step',
    'properties.bootstrap.servers' = 'analytics-kafka:9092',
    'key.format' = 'json',
    'value.format' = 'json'
);

CREATE TABLE upsert_ods_usage_event (
    id          BIGINT,
    tenant_id   STRING,
    meter       STRING,
    operation   STRING,
    request_id  STRING,
    window_key  STRING,
    amount      STRING,
    ref_type    STRING,
    ref_id      STRING,
    created_at  STRING,
    dt          STRING,
    PRIMARY KEY (id) NOT ENFORCED
) WITH (
    'connector' = 'upsert-kafka',
    'topic' = 'ods_usage_event',
    'properties.bootstrap.servers' = 'analytics-kafka:9092',
    'key.format' = 'json',
    'value.format' = 'json'
);

CREATE TABLE upsert_ods_agent_task (
    id                BIGINT,
    request_id        STRING,
    user_id           STRING,
    conversation_id   STRING,
    knowledge_base_id STRING,
    status            STRING,
    current_run_id    STRING,
    created_at        STRING,
    dt                STRING,
    PRIMARY KEY (id) NOT ENFORCED
) WITH (
    'connector' = 'upsert-kafka',
    'topic' = 'ods_agent_task',
    'properties.bootstrap.servers' = 'analytics-kafka:9092',
    'key.format' = 'json',
    'value.format' = 'json'
);

-- ── plain kafka sources:实时指标读取(upsert topic 的 value 流 = 最新值) ───
CREATE TABLE realtime_model_usage_record (
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
    'properties.group.id' = 'flink_analytics_rt',
    'scan.startup.mode' = 'latest-offset',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

-- ── MySQL JDBC sink:实时指标(V82 建表;upsert by window/tenant/model) ─────
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
    'username' = 'hfusionhub',
    'password' = 'CHANGE_ME',
    'sink.buffer-flush.max-rows' = '200',
    'sink.buffer-flush.interval' = '5s'
);

-- ── 透传视图(供 TUMBLE TVF 消费;watermark 随源) ───────────────────────────
CREATE TEMPORARY VIEW aggregated_stream AS
SELECT
    row_time                                 AS row_time,
    CAST(tenant_id AS BIGINT)                AS tenant_id,
    model,
    total_tokens,
    CAST(cost_usd AS DECIMAL(12, 6))         AS cost_usd,
    latency_ms
FROM realtime_model_usage_record;
