-- ============================================================================
-- HFusionData Analytics — 04 DWD 明细事实层
-- 由 PySpark 作业(dwd_transform.py)清洗/回补租户后写 Parquet:
--   * tenant 回补: model_usage_record.tenant_id 为空时经 agent_run/user 链补齐
--   * 标准化: 分区 dt 取事件日期;字段与 ODS 对齐但保证 tenant_id 非空分析口径
--   * 幂等: 按 dt 分区 INSERT OVERWRITE,任意历史日可回补
-- 本文件是对产出 Parquet 的外部表声明(存储计算解耦,见架构文档 2.3)。
-- ============================================================================

CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.dwd_llm_call (
    tenant_id         BIGINT      COMMENT '租户ID(回补后非空)',
    user_id           BIGINT,
    conversation_id   BIGINT,
    agent_task_id     BIGINT,
    model             STRING,
    provider          STRING,
    request_type      STRING      COMMENT 'chat|embedding|agent|evaluation',
    prompt_tokens     INT,
    completion_tokens INT,
    total_tokens      INT,
    cost_usd          DECIMAL(12,6),
    latency_ms        INT,
    created_at        TIMESTAMP,
    event_date        STRING      COMMENT '事件真实日期(可能与导入 dt 不同,回补口径)'
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dwd/dwd_llm_call';

CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.dwd_agent_step (
    tenant_id    BIGINT      COMMENT '经 run 链回补',
    run_id       BIGINT,
    sequence     INT,
    step_type    STRING,
    action       STRING,
    duration_ms  BIGINT,
    error_code   STRING,
    is_error     BOOLEAN     COMMENT 'error_code 非空即异常步',
    created_at   TIMESTAMP,
    event_date   STRING
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dwd/dwd_agent_step';

CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.dwd_usage_event (
    tenant_id   BIGINT,
    meter       STRING,
    operation   STRING,
    request_id  STRING,
    window_key  STRING,
    amount      BIGINT,
    ref_type    STRING,
    ref_id      STRING,
    created_at  TIMESTAMP,
    event_date  STRING
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dwd/dwd_usage_event';

CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.dwd_agent_run (
    tenant_id        BIGINT,
    task_id          BIGINT,
    run_uuid         STRING,
    attempt_number   INT,
    status           STRING,
    model            STRING,
    tool_calls_count INT,
    error_code       STRING,
    failed_tool      STRING,
    duration_ms      BIGINT,
    created_at       TIMESTAMP,
    event_date       STRING
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dwd/dwd_agent_run';

-- 评测明细(含派生指标:检索命中集合交并)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.dwd_eval_record (
    query_id               STRING,
    query                  STRING,
    final_status           STRING,
    ttft_ms                BIGINT,
    latency_ms             BIGINT,
    requires_rag           BOOLEAN,
    expected_document_ids  ARRAY<STRING>,
    retrieved_document_ids ARRAY<STRING>,
    hit_count              INT      COMMENT '期望文档命中数',
    expected_count         INT,
    hit_ratio              DOUBLE   COMMENT 'hit_count / expected_count'
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dwd/dwd_eval_record';
