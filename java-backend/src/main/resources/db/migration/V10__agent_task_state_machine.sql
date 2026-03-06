-- =====================================================
-- HFusionHub V10 — Agent 持久化任务状态机
-- 新增三类表: agent_task（任务）、agent_run（执行）、agent_step（步骤）
-- =====================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- =====================================================
-- Agent 任务表 (agent_task) — 每次用户请求一条记录
-- =====================================================
CREATE TABLE IF NOT EXISTS `agent_task` (
    `id`               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '任务ID',
    `request_id`       VARCHAR(64)  NOT NULL                COMMENT '客户端幂等键',
    `user_id`          BIGINT       NOT NULL                COMMENT '用户ID',
    `conversation_id`  BIGINT       NOT NULL                COMMENT '对话ID',
    `knowledge_base_id` BIGINT      DEFAULT NULL            COMMENT '知识库ID(可选)',
    `query`            TEXT         NOT NULL                COMMENT '原始问题',
    `status`           VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT 'pending|running|waiting_approval|succeeded|failed|cancelled|timed_out',
    `current_run_id`   BIGINT       DEFAULT NULL            COMMENT '当前活跃run的ID',
    `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_task_request_id` (`request_id`),
    INDEX `idx_task_user_status` (`user_id`, `status`),
    INDEX `idx_task_conv` (`conversation_id`),
    INDEX `idx_task_created_at` (`created_at`),
    CONSTRAINT `fk_task_user` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`),
    CONSTRAINT `fk_task_conv` FOREIGN KEY (`conversation_id`) REFERENCES `conversation` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent任务表';

-- =====================================================
-- Agent 运行记录表 (agent_run) — 每次执行尝试一条记录
-- =====================================================
CREATE TABLE IF NOT EXISTS `agent_run` (
    `id`               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '运行ID',
    `task_id`          BIGINT       NOT NULL                COMMENT '关联任务ID',
    `run_uuid`         VARCHAR(36)  NOT NULL                COMMENT 'UUID,对应Python的agent_run_id',
    `attempt_number`   INT          NOT NULL DEFAULT 1      COMMENT '第N次尝试(1-based)',
    `status`           VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT 'pending|running|succeeded|failed|cancelled|timed_out',
    `model`            VARCHAR(50)  DEFAULT NULL            COMMENT '使用的模型',
    `style`            VARCHAR(20)  DEFAULT 'detailed'      COMMENT '回答风格',
    `max_tool_steps`   INT          DEFAULT 5               COMMENT '最大工具步数',
    `token_usage`      JSON         DEFAULT NULL            COMMENT 'token统计{total_tokens,prompt_tokens,completion_tokens}',
    `tool_calls_count` INT          DEFAULT 0               COMMENT '工具调用次数',
    `error_code`       VARCHAR(50)  DEFAULT NULL            COMMENT '错误码:timeout|connection_error|tool_error|internal_error|cancelled',
    `error_detail`     TEXT         DEFAULT NULL            COMMENT '错误详情',
    `failed_tool`      VARCHAR(50)  DEFAULT NULL            COMMENT '失败的工具名',
    `started_at`       DATETIME     DEFAULT NULL            COMMENT '开始执行时间',
    `completed_at`     DATETIME     DEFAULT NULL            COMMENT '完成时间',
    `duration_ms`      BIGINT       DEFAULT 0               COMMENT '执行耗时(毫秒)',
    `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_run_uuid` (`run_uuid`),
    INDEX `idx_run_task_id` (`task_id`),
    INDEX `idx_run_status` (`status`),
    CONSTRAINT `fk_run_task` FOREIGN KEY (`task_id`) REFERENCES `agent_task` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent运行记录表';

-- =====================================================
-- Agent 步骤记录表 (agent_step) — 每次工具调用/检索/生成一条
-- =====================================================
CREATE TABLE IF NOT EXISTS `agent_step` (
    `id`              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '步骤ID',
    `run_id`          BIGINT       NOT NULL                COMMENT '关联运行ID',
    `sequence`        INT          NOT NULL DEFAULT 0      COMMENT '步骤序号(从1开始)',
    `step_type`       VARCHAR(30)  NOT NULL                COMMENT 'intent_classification|retrieval|tool_call|model_generation|reflection|grounding_check',
    `action`          VARCHAR(50)  DEFAULT NULL            COMMENT '工具名或阶段名',
    `input_summary`   TEXT         DEFAULT NULL            COMMENT '输入摘要(截断)',
    `output_summary`  TEXT         DEFAULT NULL            COMMENT '输出摘要(截断)',
    `sources`         JSON         DEFAULT NULL            COMMENT '引用来源',
    `duration_ms`     BIGINT       DEFAULT 0               COMMENT '此步耗时(毫秒)',
    `error_code`      VARCHAR(50)  DEFAULT NULL            COMMENT '错误码',
    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    INDEX `idx_step_run_seq` (`run_id`, `sequence`),
    CONSTRAINT `fk_step_run` FOREIGN KEY (`run_id`) REFERENCES `agent_run` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent步骤记录表';

-- agent_task.current_run_id 自引用外键（agent_run 表已存在后添加）
ALTER TABLE `agent_task`
    ADD CONSTRAINT `fk_task_current_run` FOREIGN KEY (`current_run_id`) REFERENCES `agent_run` (`id`);
