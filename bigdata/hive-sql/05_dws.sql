-- ============================================================================
-- HFusionData Analytics — 05 DWS 汇总层
-- 粒度声明与主键(去重键)写在表注释;PySpark dws_aggregate.py 写入,
-- 同粒度物化视图口径保持一致(见 07_query_examples.sql 的对照查询)。
-- ============================================================================

-- 租户 × 模型 × 日:token/成本/延迟核心口径
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.dws_tenant_model_daily (
    tenant_id         BIGINT,
    model             STRING,
    stat_date         STRING,
    call_count        BIGINT,
    prompt_tokens     BIGINT,
    completion_tokens BIGINT,
    total_tokens      BIGINT,
    cost_usd          DECIMAL(12,6),
    avg_latency_ms    BIGINT,
    p95_latency_ms    BIGINT   COMMENT 'approx_percentile(0.95)'
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dws/dws_tenant_model_daily';

-- 租户 × 步骤类型 × 日:Agent 执行健康度
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.dws_tenant_step_daily (
    tenant_id        BIGINT,
    step_type        STRING,
    stat_date        STRING,
    step_count       BIGINT,
    error_count      BIGINT,
    error_rate       DOUBLE,
    avg_duration_ms  BIGINT
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dws/dws_tenant_step_daily';

-- 租户 × 计量项 × 日:账本口径(RESERVE/COMMIT/RELEASE 分列)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.dws_tenant_meter_daily (
    tenant_id       BIGINT,
    meter           STRING,
    stat_date       STRING,
    reserve_amount  BIGINT,
    commit_amount   BIGINT,
    release_amount  BIGINT,
    event_count     BIGINT
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dws/dws_tenant_meter_daily';

-- 全平台 × 模型 × 日:模型维度聚合(成本页/大屏模型占比)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.dws_model_daily (
    model             STRING,
    stat_date         STRING,
    call_count        BIGINT,
    total_tokens      BIGINT,
    cost_usd          DECIMAL(12,6),
    avg_latency_ms    BIGINT,
    p95_latency_ms    BIGINT
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dws/dws_model_daily';
