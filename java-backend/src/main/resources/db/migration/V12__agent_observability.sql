-- =====================================================
-- HFusionHub V12 — Agent 评测与可观测性
-- 新增: agent_evaluation_dataset, agent_evaluation_case,
--       agent_evaluation_run, agent_alert_rule, agent_alert_event
-- =====================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- =====================================================
-- 离线评测集元数据表
-- =====================================================
CREATE TABLE IF NOT EXISTS `agent_evaluation_dataset` (
    `id`                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '评测集ID',
    `name`              VARCHAR(200) NOT NULL                COMMENT '评测集名称',
    `description`       TEXT         DEFAULT NULL            COMMENT '评测集描述',
    `knowledge_base_id` BIGINT       DEFAULT NULL            COMMENT '关联知识库ID(可选,跨库评测时为NULL)',
    `user_id`           BIGINT       NOT NULL                COMMENT '创建者用户ID',
    `dimensions`        JSON         NOT NULL                COMMENT '覆盖的评测维度 ["answer_correctness","citation_consistency","privilege_containment","tool_success_rate"]',
    `case_count`        INT          NOT NULL DEFAULT 0      COMMENT '用例数量',
    `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX `idx_eval_dataset_user` (`user_id`),
    INDEX `idx_eval_dataset_kb` (`knowledge_base_id`),
    CONSTRAINT `fk_eval_dataset_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent离线评测集表';

-- =====================================================
-- 评测用例表
-- =====================================================
CREATE TABLE IF NOT EXISTS `agent_evaluation_case` (
    `id`                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '用例ID',
    `dataset_id`        BIGINT       NOT NULL                COMMENT '所属评测集ID',
    `query`             TEXT         NOT NULL                COMMENT '测试查询',
    `expected_answer`   TEXT         DEFAULT NULL            COMMENT '期望答案(ground truth)',
    `expected_sources`  JSON         DEFAULT NULL            COMMENT '期望引用的文档ID列表 ["doc_id_1","doc_id_2"]',
    `privilege_test`    JSON         DEFAULT NULL            COMMENT '越权测试配置 {"target_kb_id":999,"expect_blocked":true}',
    `metadata`          JSON         DEFAULT NULL            COMMENT '用例元数据(标签、难度等)',
    `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    INDEX `idx_eval_case_dataset` (`dataset_id`),
    CONSTRAINT `fk_eval_case_dataset` FOREIGN KEY (`dataset_id`) REFERENCES `agent_evaluation_dataset` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent评测用例表';

-- =====================================================
-- 评测执行记录表
-- =====================================================
CREATE TABLE IF NOT EXISTS `agent_evaluation_run` (
    `id`                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '执行记录ID',
    `dataset_id`        BIGINT       NOT NULL                COMMENT '评测集ID',
    `run_uuid`          VARCHAR(36)  NOT NULL                COMMENT '执行UUID',
    `status`            VARCHAR(20)  NOT NULL DEFAULT 'running' COMMENT 'running|completed|failed',
    `overall_score`     DECIMAL(6,4) DEFAULT NULL            COMMENT '综合得分(0-1)',
    `dimension_scores`  JSON         DEFAULT NULL            COMMENT '各维度得分 {"answer_correctness":0.85,"citation_consistency":0.92}',
    `case_results`      JSON         DEFAULT NULL            COMMENT '各用例结果摘要',
    `failed_case_ids`   JSON         DEFAULT NULL            COMMENT '未通过用例ID列表',
    `error_detail`      TEXT         DEFAULT NULL            COMMENT '错误详情(如果failed)',
    `created_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_eval_run_uuid` (`run_uuid`),
    INDEX `idx_eval_run_dataset` (`dataset_id`),
    INDEX `idx_eval_run_created` (`created_at`),
    CONSTRAINT `fk_eval_run_dataset` FOREIGN KEY (`dataset_id`) REFERENCES `agent_evaluation_dataset` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent评测执行记录表';

-- =====================================================
-- 告警规则配置表
-- =====================================================
CREATE TABLE IF NOT EXISTS `agent_alert_rule` (
    `id`                  BIGINT       NOT NULL AUTO_INCREMENT COMMENT '规则ID',
    `name`                VARCHAR(200) NOT NULL                COMMENT '规则名称',
    `description`         TEXT         DEFAULT NULL            COMMENT '规则描述',
    `user_id`             BIGINT       DEFAULT NULL            COMMENT '用户ID(NULL=全局规则)',
    `metric_name`         VARCHAR(50)  NOT NULL                COMMENT '监控指标名: citation_miss_rate|tool_failure_rate|running_timeout|approval_timeout',
    `comparison_operator` VARCHAR(10)  NOT NULL DEFAULT 'gte'  COMMENT '比较符: gt|gte|lt|lte|eq',
    `threshold_value`     DECIMAL(12,4) NOT NULL               COMMENT '阈值',
    `window_minutes`      INT          NOT NULL DEFAULT 60     COMMENT '评估窗口(分钟)',
    `severity`            VARCHAR(10)  NOT NULL DEFAULT 'warning' COMMENT '严重度: critical|warning|info',
    `cooldown_minutes`    INT          NOT NULL DEFAULT 60     COMMENT '冷却时间(分钟,防重复告警)',
    `enabled`             TINYINT(1)   NOT NULL DEFAULT 1      COMMENT '是否启用',
    `last_triggered_at`   DATETIME     DEFAULT NULL            COMMENT '上次触发时间',
    `created_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX `idx_alert_rule_user` (`user_id`),
    INDEX `idx_alert_rule_metric` (`metric_name`),
    INDEX `idx_alert_rule_enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent告警规则配置表';

-- =====================================================
-- 告警事件记录表
-- =====================================================
CREATE TABLE IF NOT EXISTS `agent_alert_event` (
    `id`              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '事件ID',
    `rule_id`         BIGINT       NOT NULL                COMMENT '触发规则ID',
    `rule_name`       VARCHAR(200) NOT NULL                COMMENT '规则名称(冗余,方便查询)',
    `user_id`         BIGINT       DEFAULT NULL            COMMENT '相关用户ID',
    `knowledge_base_id` BIGINT     DEFAULT NULL            COMMENT '相关知识库ID',
    `severity`        VARCHAR(10)  NOT NULL                COMMENT '严重度: critical|warning|info',
    `metric_name`     VARCHAR(50)  NOT NULL                COMMENT '指标名',
    `current_value`   DECIMAL(12,4) NOT NULL               COMMENT '当前指标值',
    `threshold_value` DECIMAL(12,4) NOT NULL               COMMENT '触发阈值',
    `message`         TEXT         NOT NULL                COMMENT '告警消息',
    `context`         JSON         DEFAULT NULL            COMMENT '上下文数据(触发时的详细指标)',
    `resolved`        TINYINT(1)   NOT NULL DEFAULT 0      COMMENT '是否已解除',
    `resolved_at`     DATETIME     DEFAULT NULL            COMMENT '解除时间',
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    INDEX `idx_alert_event_rule` (`rule_id`),
    INDEX `idx_alert_event_user` (`user_id`),
    INDEX `idx_alert_event_severity` (`severity`),
    INDEX `idx_alert_event_created` (`created_at`),
    INDEX `idx_alert_event_resolved` (`resolved`, `created_at`),
    CONSTRAINT `fk_alert_event_rule` FOREIGN KEY (`rule_id`) REFERENCES `agent_alert_rule` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent告警事件记录表';

-- =====================================================
-- 预置告警规则 (全局默认)
-- =====================================================
INSERT INTO `agent_alert_rule` (`name`, `description`, `user_id`, `metric_name`, `comparison_operator`, `threshold_value`, `window_minutes`, `severity`, `cooldown_minutes`) VALUES
('引用缺失告警', '无sources的completed Run占比超过阈值时触发', NULL, 'citation_miss_rate', 'gte', 0.10, 1440, 'warning', 120),
('工具失败率告警', 'tool_error终态占比超过阈值时触发', NULL, 'tool_failure_rate', 'gte', 0.20, 60, 'critical', 30),
('异常运行超时告警', '存在running状态超过120秒的Run时触发', NULL, 'running_timeout', 'gte', 1.00, 5, 'critical', 10),
('审批超时告警', '存在pending超过4分钟的审批时触发', NULL, 'approval_timeout', 'gte', 1.00, 5, 'warning', 10);
