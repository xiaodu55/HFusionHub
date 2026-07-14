-- ============================================================================
-- HFusionData Analytics — Flink CDC 增量采集:MySQL binlog → Kafka(JSON)
-- 提交: sql-client.sh -f cdc_ingest.sql(密码 {PWD} 由部署替换;
--       connector jar 安装见 README.md)
-- 设计: 'scan.startup.mode'='initial' 首次全量快照 + binlog 增量;
--       断点续传由 Flink checkpoint 保证;主产品零侵入(只读 binlog)。
-- ============================================================================


CREATE TABLE cdc_model_usage_record (
  id BIGINT, user_id BIGINT, tenant_id BIGINT, conversation_id BIGINT,
  agent_task_id BIGINT, model STRING, provider STRING, prompt_tokens INT,
  completion_tokens INT, total_tokens INT, cost_usd DECIMAL(12,6), latency_ms INT,
  request_type STRING, created_at TIMESTAMP
) WITH (
    'connector' = 'mysql-cdc',
    'hostname' = 'mysql8',
    'port' = '3306',
    'username' = 'hfusionhub',
    'password' = 'CHANGE_ME',
    'database-name' = 'hfusionhub',
    'table-name' = 'model_usage_record',
    'scan.startup.mode' = 'initial',
    'scan.incremental.snapshot.enabled' = 'true',
    'scan.incremental.snapshot.chunk.key-column' = 'id',
    'debezium.database.allowPublicKeyRetrieval' = 'true'
);

CREATE TABLE cdc_agent_step (
  id BIGINT, run_id BIGINT, sequence INT, step_type STRING, action STRING,
  duration_ms BIGINT, error_code STRING, created_at TIMESTAMP
) WITH (
    'connector' = 'mysql-cdc',
    'hostname' = 'mysql8',
    'port' = '3306',
    'username' = 'hfusionhub',
    'password' = 'CHANGE_ME',
    'database-name' = 'hfusionhub',
    'table-name' = 'agent_step',
    'scan.startup.mode' = 'initial',
    'scan.incremental.snapshot.enabled' = 'true',
    'scan.incremental.snapshot.chunk.key-column' = 'id',
    'debezium.database.allowPublicKeyRetrieval' = 'true'
);

CREATE TABLE cdc_usage_event (
  id BIGINT, tenant_id BIGINT, meter STRING, operation STRING, request_id STRING,
  window_key STRING, amount BIGINT, ref_type STRING, ref_id STRING, created_at TIMESTAMP
) WITH (
    'connector' = 'mysql-cdc',
    'hostname' = 'mysql8',
    'port' = '3306',
    'username' = 'hfusionhub',
    'password' = 'CHANGE_ME',
    'database-name' = 'hfusionhub',
    'table-name' = 'usage_event',
    'scan.startup.mode' = 'initial',
    'scan.incremental.snapshot.enabled' = 'true',
    'scan.incremental.snapshot.chunk.key-column' = 'id',
    'debezium.database.allowPublicKeyRetrieval' = 'true'
);

CREATE TABLE cdc_agent_task (
  id BIGINT, request_id STRING, user_id BIGINT, conversation_id BIGINT,
  knowledge_base_id BIGINT, status STRING, current_run_id BIGINT, created_at TIMESTAMP
) WITH (
    'connector' = 'mysql-cdc',
    'hostname' = 'mysql8',
    'port' = '3306',
    'username' = 'hfusionhub',
    'password' = 'CHANGE_ME',
    'database-name' = 'hfusionhub',
    'table-name' = 'agent_task',
    'scan.startup.mode' = 'initial',
    'scan.incremental.snapshot.enabled' = 'true',
    'scan.incremental.snapshot.chunk.key-column' = 'id',
    'debezium.database.allowPublicKeyRetrieval' = 'true'
);

EXECUTE STATEMENT SET BEGIN
INSERT INTO upsert_ods_model_usage_record
SELECT id, CAST(user_id AS STRING), CAST(tenant_id AS STRING),
       CAST(conversation_id AS STRING), CAST(agent_task_id AS STRING),
       model, provider, prompt_tokens, completion_tokens, total_tokens,
       CAST(cost_usd AS STRING), latency_ms, request_type,
       DATE_FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss'),
       DATE_FORMAT(created_at, 'yyyy-MM-dd')
FROM cdc_model_usage_record;

INSERT INTO upsert_ods_agent_step
SELECT id, CAST(run_id AS STRING), CAST(sequence AS STRING),
       step_type, action, duration_ms, error_code,
       DATE_FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss'),
       DATE_FORMAT(created_at, 'yyyy-MM-dd')
FROM cdc_agent_step;

INSERT INTO upsert_ods_usage_event
SELECT id, CAST(tenant_id AS STRING), meter, operation,
       request_id, window_key, CAST(amount AS STRING), ref_type, ref_id,
       DATE_FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss'),
       DATE_FORMAT(created_at, 'yyyy-MM-dd')
FROM cdc_usage_event;

INSERT INTO upsert_ods_agent_task
SELECT id, request_id, CAST(user_id AS STRING),
       CAST(conversation_id AS STRING), CAST(knowledge_base_id AS STRING),
       status, CAST(current_run_id AS STRING),
       DATE_FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss'),
       DATE_FORMAT(created_at, 'yyyy-MM-dd')
FROM cdc_agent_task;
END;
