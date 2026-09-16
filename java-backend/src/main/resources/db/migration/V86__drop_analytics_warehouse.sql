-- V86: 移除运营数仓扩展包的应用层表（2026-09-22 架构减法）
-- =====================================================
-- HFusionData Analytics（分析扩展包）整体迁出至独立仓库
-- github.com/xiaodu55/HFusionData：调度器 / 执行器 / Controller /
-- Ads* 与实时指标实体随迁，主平台不再有代码读写这些表。
-- V82 / V83 作为迁移链历史保留；本迁移清理其产物。
-- 注意：DROP 会丢弃历史数据，如需保留请先自行归档。
-- =====================================================

DROP TABLE IF EXISTS ads_eval_quality;
DROP TABLE IF EXISTS ads_tool_success;
DROP TABLE IF EXISTS ads_tenant_topn;
DROP TABLE IF EXISTS ads_model_share;
DROP TABLE IF EXISTS ads_cost_daily;
DROP TABLE IF EXISTS analytics_realtime_metrics;
DROP TABLE IF EXISTS bigdata_batch_run_log;
DROP TABLE IF EXISTS table_lineage;
