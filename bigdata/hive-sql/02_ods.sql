-- ============================================================================
-- HFusionData Analytics — 02 ODS 操作数据层
-- 外部表 + dt 分区,Parquet(评测 JSONL 为 JSON SerDe)。数据由两条链路写入:
--   全量: bigdata/scripts/full_import.py(Spark JDBC,幂等覆盖 dt 分区)
--   增量: Flink CDC(binlog→Kafka→HDFS,同一路径追加)
-- 敏感边界: sys_user 只导分析所需列,密码/手机号/邮箱不进数仓。
-- ============================================================================

-- 模型调用事实(每次 LLM 调用一行)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ods_model_usage_record (
    id                BIGINT,
    user_id           BIGINT,
    tenant_id         BIGINT,
    conversation_id   BIGINT,
    agent_task_id     BIGINT,
    model             STRING,
    provider          STRING,
    prompt_tokens     INT,
    completion_tokens INT,
    total_tokens      INT,
    cost_usd          DECIMAL(12,6),
    latency_ms        INT,
    request_type      STRING,
    created_at        TIMESTAMP
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ods/model_usage_record';

-- Agent 工具步事实(每工具调用/检索/生成一行;无 tenant_id,DWD 回补)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ods_agent_step (
    id             BIGINT,
    run_id         BIGINT,
    sequence       INT,
    step_type      STRING,
    action         STRING,
    duration_ms    BIGINT,
    error_code     STRING,
    created_at     TIMESTAMP
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ods/agent_step';

-- 用量账本事件(追加式:RESERVE/COMMIT/RELEASE)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ods_usage_event (
    id          BIGINT,
    tenant_id   BIGINT,
    meter       STRING,
    operation   STRING,
    request_id  STRING,
    window_key  STRING,
    amount      BIGINT,
    ref_type    STRING,
    ref_id      STRING,
    created_at  TIMESTAMP
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ods/usage_event';

-- Agent 任务事实(无 tenant_id,DWD 回补)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ods_agent_task (
    id                BIGINT,
    request_id        STRING,
    user_id           BIGINT,
    conversation_id   BIGINT,
    knowledge_base_id BIGINT,
    status            STRING,
    current_run_id    BIGINT,
    created_at        TIMESTAMP
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ods/agent_task';

-- Agent 运行事实(含 tenant_id 回填列与失败信息)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ods_agent_run (
    id               BIGINT,
    task_id          BIGINT,
    run_uuid         STRING,
    attempt_number   INT,
    status           STRING,
    model            STRING,
    tool_calls_count INT,
    error_code       STRING,
    failed_tool      STRING,
    duration_ms      BIGINT,
    created_at       TIMESTAMP
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ods/agent_run';

-- 用户维表源(仅分析列)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ods_sys_user (
    id          BIGINT,
    username    STRING,
    role        STRING,
    status      TINYINT,
    created_at  TIMESTAMP
)
PARTITIONED BY (dt STRING)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/ods/sys_user';

-- 评测逐样本记录(Python eval_harness JSONL,JSON SerDe)
CREATE EXTERNAL TABLE IF NOT EXISTS hfusionhub.ods_eval_record (
    query_id               STRING,
    query                  STRING,
    answer                 STRING,
    ttft_ms                BIGINT,
    latency_ms             BIGINT,
    final_status           STRING,
    requires_rag           BOOLEAN,
    expected_document_ids  STRING,
    retrieved_document_ids STRING,
    error                  STRING,
    recorded_at            STRING
)
PARTITIONED BY (dt STRING)
ROW FORMAT SERDE 'org.apache.hive.hcatalog.data.JsonSerDe'
STORED AS TEXTFILE
LOCATION '/warehouse/hfusionhub/ods/eval_record';

-- 手动补分区示例(全量导入新 dt 后执行,或开 MSCK):
-- ALTER TABLE hfusionhub.ods_model_usage_record ADD IF NOT EXISTS PARTITION (dt='2026-08-30');
