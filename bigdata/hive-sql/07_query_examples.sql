-- ============================================================================
-- HFusionData Analytics — 07 Beeline 查询示例与分区管理
-- 连接: beeline -u jdbc:hive2://hive-server2:10000 -n hfusion
-- ============================================================================

USE hfusionhub;

-- ── 分区管理:全量导入/Flink 落地新 dt 后(若未开自动同步) ────────────────
-- MSCK 一次修复所有外部表(Parquet 路径含 dt= 子目录时生效):
-- MSCK REPAIR TABLE ods_model_usage_record;
-- MSCK REPAIR TABLE ods_agent_step;
-- MSCK REPAIR TABLE ods_agent_task;
-- MSCK REPAIR TABLE ods_agent_run;
-- MSCK REPAIR TABLE ods_usage_event;
-- MSCK REPAIR TABLE ods_sys_user;
-- MSCK REPAIR TABLE ods_eval_record;

-- ── 运营日报样例(ADS 同构口径,可直接对照 Spark 产出校验) ───────────────

-- 1. 某租户近 7 天每日成本与 token
SELECT stat_date, call_count, total_tokens, cost_usd
FROM dws_tenant_model_daily
WHERE tenant_id = 1 AND stat_date >= date_sub(current_date, 6)
GROUP BY stat_date, call_count, total_tokens, cost_usd
ORDER BY stat_date;

-- 2. 模型成本占比(平台口径,指定日)
SELECT model, cost_usd,
       ROUND(cost_usd / SUM(cost_usd) OVER (), 4) AS cost_share
FROM dws_model_daily
WHERE stat_date = '2026-08-30';

-- 3. Agent 步骤健康度:错误率 Top
SELECT step_type, step_count, error_count, ROUND(error_rate, 4) AS err_rate
FROM dws_tenant_step_daily
WHERE tenant_id = 1 AND stat_date >= date_sub(current_date, 6)
ORDER BY error_rate DESC;

-- 4. 账本对账:同窗口 RESERVE vs COMMIT(预占泄漏检测)
SELECT meter, window_key,
       SUM(CASE WHEN operation = 'RESERVE' THEN amount ELSE 0 END) AS reserved,
       SUM(CASE WHEN operation = 'COMMIT'  THEN amount ELSE 0 END) AS committed,
       SUM(CASE WHEN operation = 'RELEASE' THEN amount ELSE 0 END) AS released
FROM ods_usage_event
GROUP BY meter, window_key
ORDER BY window_key DESC;

-- 5. 评测质量趋势
SELECT stat_date, ROUND(avg_hit_ratio, 4) AS hit_ratio,
       ROUND(failure_rate, 4) AS fail_rate, avg_latency_ms
FROM ads_eval_quality
ORDER BY stat_date DESC LIMIT 30;
