-- ============================================================================
-- HFusionData Analytics — ODS 落地:Kafka(JSON) → HDFS Parquet(按 dt 分区)
--
-- 设计:与全量导入(full_import.py)写同一目录 /warehouse/hfusionhub/ods/<table>,
-- dt=处理日期分区;Hive 外部表指向该路径,全量 + 增量两条链路自然合流。
-- 幂等:filesystem sink 按 dt 滚动新分区文件;重放由 checkpoint 恢复保证不重。
--
-- 提交: sql-client.sh -f /opt/flink/usrlib/analytics/ods_filesink.sql
-- ============================================================================

-- 以下 catalog/source/sink DDL 已在 00_catalogs.sql 定义;此处 INSERT 部分:
EXECUTE STATEMENT SET BEGIN

INSERT INTO hdfs_ods_model_usage_record
SELECT user_id, tenant_id, conversation_id, agent_task_id, model, provider,
       prompt_tokens, completion_tokens, total_tokens, cost_usd, latency_ms,
       request_type, created_at, dt
FROM kafka_ods_model_usage_record;

INSERT INTO hdfs_ods_agent_step
SELECT run_id, sequence, step_type, action, duration_ms, error_code,
       created_at, dt
FROM kafka_ods_agent_step;

INSERT INTO hdfs_ods_usage_event
SELECT tenant_id, meter, operation, request_id, window_key, amount,
       ref_type, ref_id, created_at, dt
FROM kafka_ods_usage_event;

INSERT INTO hdfs_ods_agent_task
SELECT request_id, user_id, conversation_id, knowledge_base_id, status,
       current_run_id, created_at, dt
FROM kafka_ods_agent_task;

END;
