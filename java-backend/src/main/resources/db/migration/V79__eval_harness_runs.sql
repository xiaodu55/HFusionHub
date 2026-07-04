-- V79: 评估中枢（eval_harness）运行记录表
-- python-ai 评估中枢的生成质量/行为红线/TTFT 评估运行摘要，供「回答效果」页
-- 列表展示与 A/B 对比选 run。详细逐样本数据仍在 python-ai 侧 JSONL/报告中，
-- 本表只存聚合摘要（与 rag_evaluation_runs SQLite 的存摘要约定一致）。

CREATE TABLE IF NOT EXISTS `eval_harness_runs` (
    `id`                  BIGINT       NOT NULL AUTO_INCREMENT COMMENT '运行ID',
    `run_file`            VARCHAR(160) NOT NULL                COMMENT 'python 侧运行文件名（<label>_<ts>.jsonl）',
    `label`               VARCHAR(64)  DEFAULT NULL            COMMENT '评估标签',
    `knowledge_base_id`   BIGINT       DEFAULT NULL            COMMENT '评测知识库ID',
    `top_k`               INT          DEFAULT 5               COMMENT '检索 Top-K',
    `record_count`        INT          DEFAULT 0               COMMENT '记录条数',
    `requires_rag_count`  INT          DEFAULT 0               COMMENT '要求 RAG 的样本数',
    `judge_enabled`       TINYINT      NOT NULL DEFAULT 0      COMMENT '是否启用 LLM 评审',
    `judge_cases`         INT          DEFAULT 0               COMMENT 'LLM 评审条数',
    `overall`             JSON         DEFAULT NULL            COMMENT '聚合指标（检索/行为/TTFT/judge）',
    `failed_case_ids`     JSON         DEFAULT NULL            COMMENT '未命中用例 ID 列表',
    `created_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `tenant_id`           BIGINT       DEFAULT NULL            COMMENT '租户ID',
    `deleted`             TINYINT      NOT NULL DEFAULT 0      COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_eval_harness_run_file` (`run_file`),
    INDEX `idx_eval_harness_created` (`created_at`),
    INDEX `idx_eval_harness_tenant` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='评估中枢运行记录';
