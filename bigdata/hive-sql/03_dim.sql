-- ============================================================================
-- HFusionData Analytics — 03 DIM 维度层
-- dim_date/dim_model 由 beeline 首启灌入(小表,managed);
-- dim_user 为 ODS 用户源的最新分区视图(每日随全量导入滚动)。
-- ============================================================================

-- ── 日期维(2026-01-01 ~ 2027-12-31,由 INSERT 生成) ──────────────────────
CREATE TABLE IF NOT EXISTS hfusionhub.dim_date (
    date_key      STRING     COMMENT 'YYYY-MM-DD',
    year          INT,
    quarter       INT,
    month         INT,
    day           INT,
    week_of_year  INT,
    day_of_week   INT        COMMENT '1=周一 ... 7=周日',
    is_weekend    BOOLEAN
)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dim/dim_date';

-- ── 模型维(与 LLM 网关 provider 清单一致;新增模型在此登记) ─────────────
CREATE TABLE IF NOT EXISTS hfusionhub.dim_model (
    model_key   STRING  COMMENT '模型标识(model_usage_record.model)',
    provider    STRING,
    model_name  STRING  COMMENT '展示名',
    input_price_per_1m  DECIMAL(10,4) COMMENT '每百万输入 token 美元(登记价)',
    output_price_per_1m DECIMAL(10,4)
)
STORED AS PARQUET
LOCATION '/warehouse/hfusionhub/dim/dim_model';

INSERT INTO hfusionhub.dim_model VALUES
    ('deepseek-v4-flash', 'deepseek',  'DeepSeek V4 Flash', 0.2700, 1.1000),
    ('deepseek-chat',     'deepseek',  'DeepSeek Chat',     0.2700, 1.1000),
    ('deepseek-reasoner', 'deepseek',  'DeepSeek Reasoner', 0.5500, 2.1900),
    ('ollama-local',      'ollama',    'Ollama 本地模型',   0.0000, 0.0000);

-- ── 用户维(视图:取 ODS 用户源最新分区;tenant_id 用于全链路租户隔离) ────
CREATE VIEW IF NOT EXISTS hfusionhub.dim_user AS
SELECT u.id AS user_key, u.username, u.role, u.status, u.dt
FROM hfusionhub.ods_sys_user u
WHERE u.dt = (SELECT MAX(dt) FROM hfusionhub.ods_sys_user);
