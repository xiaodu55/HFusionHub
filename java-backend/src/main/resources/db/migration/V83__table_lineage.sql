-- HFusionData Analytics — 表级血缘元数据(V83,轻量数据治理)
-- 由 bigdata/lineage/load_lineage.py 从 lineage.yaml 注册表加载;
-- 消费方:血缘可视化 / 影响分析(上游表变更时反查受看板)。
-- 平台级治理表,tenant_id = -1(平台口径,与 ADS 镜像表约定一致)。

CREATE TABLE IF NOT EXISTS table_lineage (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    tenant_id    BIGINT       NOT NULL DEFAULT -1 COMMENT '平台口径固定 -1',
    job_name     VARCHAR(200) NOT NULL COMMENT '流水线作业名',
    layer        VARCHAR(20)  NOT NULL COMMENT '层级:采集/维度/明细/汇总/应用/质量/实时/湖表/消费',
    source_table VARCHAR(200) NOT NULL COMMENT '来源表(存储:表名)',
    target_table VARCHAR(200) NOT NULL COMMENT '目标表(存储:表名)',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_job_src_tgt (job_name, source_table, target_table),
    KEY idx_source (source_table),
    KEY idx_target (target_table)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '表级血缘(轻量数据治理)';
