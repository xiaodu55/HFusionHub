-- ============================================================================
-- HFusionData Analytics — 06 ADS 应用层
-- 直接服务两处消费端:
--   1) Superset 报表(Hive/ClickHouse 直查)
--   2) Java AnalyticsController —— ads_build.py 会把同构结果回写 MySQL
--      hfusionhub.ads_*(V82 迁移),业务侧零 Hadoop 依赖读取
-- 全部带 tenant_id:租户大屏强制按登录租户过滤(服务端校验)。
-- ============================================================================

-- 每日成本趋势(平台/租户)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ads_cost_daily (
    tenant_id      BIGINT        COMMENT '-1 表示平台全局口径',
    stat_date      STRING,
    call_count     BIGINT,
    total_tokens   BIGINT,
    cost_usd       DECIMAL(12,6),
    est_month_cost DECIMAL(12,2) COMMENT '线性外推月费'
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ads/ads_cost_daily';

-- 模型成本占比(平台口径 + 租户口径两份)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ads_model_share (
    tenant_id    BIGINT,
    model        STRING,
    stat_date    STRING,
    call_count   BIGINT,
    cost_usd     DECIMAL(12,6),
    cost_share   DOUBLE   COMMENT '当日该模型成本占比 0-1'
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ads/ads_model_share';

-- 租户用量 TopN(平台管理员视图)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ads_tenant_topn (
    stat_date    STRING,
    rank_no      INT,
    tenant_id    BIGINT,
    call_count   BIGINT,
    total_tokens BIGINT,
    cost_usd     DECIMAL(12,6)
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ads/ads_tenant_topn';

-- 工具成功率(租户 × 步骤类型近 7 天滚动)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ads_tool_success (
    tenant_id    BIGINT,
    step_type    STRING,
    stat_date    STRING,
    step_count   BIGINT,
    error_count  BIGINT,
    success_rate DOUBLE
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ads/ads_tool_success';

-- 检索质量趋势(评测链路:hit_ratio/延迟按日)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ads_eval_quality (
    tenant_id     BIGINT      COMMENT '评测 run 归属租户,平台跑批为 -1',
    stat_date     STRING,
    eval_count    BIGINT,
    avg_hit_ratio DOUBLE,
    avg_ttft_ms   BIGINT,
    avg_latency_ms BIGINT,
    failure_rate  DOUBLE      COMMENT 'final_status != completed 占比'
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ads/ads_eval_quality';

-- 数据质量报告(quality_check.py 产出;不合格阻断下游 ADS)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.quality_report (
    stat_date    STRING,
    table_name   STRING,
    rule_name    STRING,
    metric_value DOUBLE,
    threshold    DOUBLE,
    passed       BOOLEAN,
    detail       STRING
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/quality/quality_report';
