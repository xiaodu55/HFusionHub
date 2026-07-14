-- ============================================================================
-- HFusionData Analytics — Flink CDC 增量采集:MySQL binlog → Kafka(JSON)
--
-- 提交方式(在 flink-jobmanager 容器内,connector jar 安装见 README.md):
--   /opt/flink/bin/sql-client.sh -f /opt/flink/usrlib/analytics/cdc_ingest.sql
--
-- 设计要点:
--   * 'scan.startup.mode'='initial':首次全量快照 + 后续 binlog 增量,
--     断点续传由 Flink checkpoint 保证(job 容器重启后从 checkpoint 恢复,
--     不重不漏 —— Exactly-Once 语义由 Kafka 事务性 sink 提供);
--   * topic 按 ods_<table> 命名,值 JSON,下游 ODS 落地与实时聚合共用;
--   * 主产品零侵入:只读 binlog,不需要业务代码做任何改动。
-- ============================================================================

CREATE CATALOG mysql_src WITH (
    'connector' = 'mysql-cdc',
    'hostname' = 'mysql8',
    'port' = '3306',
    'username' = 'hfusion',            -- 与 ANALYTICS_DB_USER 保持一致
    'password' = 'CHANGE_ME',          -- 生产环境从 secret 注入,勿提交真实值
    'database-name' = 'hfusionhub',
    'debezium.snapshot.mode' = 'initial'
);

-- ── 模型调用事实(binlog → Kafka) ─────────────────────────────────────────
EXECUTE STATEMENT SET BEGIN

INSERT INTO kafka_ods_model_usage_record
SELECT CAST(id AS STRING), CAST(user_id AS STRING), CAST(tenant_id AS STRING),
       CAST(conversation_id AS STRING), CAST(agent_task_id AS STRING),
       model, provider, prompt_tokens, completion_tokens, total_tokens,
       CAST(cost_usd AS STRING), latency_ms, request_type,
       DATE_FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss'),
       DATE_FORMAT(created_at, 'yyyy-MM-dd')
FROM mysql_src.hfusionhub.model_usage_record;

-- ── Agent 工具步事实(注意:无 tenant_id,DWD 层经 dim_user 回补) ──────────
INSERT INTO kafka_ods_agent_step
SELECT CAST(id AS STRING), CAST(run_id AS STRING), CAST(sequence AS STRING),
       step_type, action, duration_ms, error_code,
       DATE_FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss'),
       DATE_FORMAT(created_at, 'yyyy-MM-dd')
FROM mysql_src.hfusionhub.agent_step;

-- ── 用量账本事件(追加式,RESERVE/COMMIT/RELEASE) ─────────────────────────
INSERT INTO kafka_ods_usage_event
SELECT CAST(id AS STRING), CAST(tenant_id AS STRING), meter, operation,
       request_id, window_key, CAST(amount AS STRING), ref_type, ref_id,
       DATE_FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss'),
       DATE_FORMAT(created_at, 'yyyy-MM-dd')
FROM mysql_src.hfusionhub.usage_event;

-- ── Agent 任务事实(无 tenant_id,同上 DWD 回补) ──────────────────────────
INSERT INTO kafka_ods_agent_task
SELECT CAST(id AS STRING), request_id, CAST(user_id AS STRING),
       CAST(conversation_id AS STRING), CAST(knowledge_base_id AS STRING),
       status, CAST(current_run_id AS STRING),
       DATE_FORMAT(created_at, 'yyyy-MM-dd HH:mm:ss'),
       DATE_FORMAT(created_at, 'yyyy-MM-dd')
FROM mysql_src.hfusionhub.agent_task;

END;
