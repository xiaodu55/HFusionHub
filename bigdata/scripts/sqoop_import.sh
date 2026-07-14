#!/usr/bin/env bash
# ============================================================================
# HFusionData Analytics — Sqoop 全量导入(经典叙事版,实验室集群用)
#
# 说明:本仓库的可运行主路径是 full_import.py(Spark JDBC,容器内开箱即用);
# 本脚本保留 Sqoop 命令单,供课程/答辩演示经典链路,或在已有 Sqoop 的
# Hadoop 集群上直接使用。逐表 --split-by 主键并行导入,--as-parquetfile。
# ============================================================================
set -euo pipefail

DT="${1:-$(date +%F)}"
CONNECT="jdbc:mysql://mysql8:3306/hfusionhub?useSSL=false&allowPublicKeyRetrieval=true"
USER="${ANALYTICS_DB_USER:-hfusionhub}"
PASS="${ANALYTICS_DB_PASSWORD:?请 export ANALYTICS_DB_PASSWORD}"
MAPRED="${MAPRED_TASKS:-4}"
TARGET="/warehouse/hfusionhub/ods"

import_one() {
  local table="$1" pk="$2"
  sqoop import \
    --connect "$CONNECT" \
    --username "$USER" --password "$PASS" \
    --table "$table" \
    --columns "$3" \
    --split-by "$pk" \
    --num-mappers "$MAPRED" \
    --as-parquetfile \
    --target-dir "$TARGET/$table/dt=$DT" \
    --delete-target-dir \
    -- --jdbc-charset utf8
  echo "[ok] $table -> $TARGET/$table/dt=$DT"
}

# 主键与列清单与 full_import.py 的 TABLE_PARTITIONS/TABLE_COLUMNS 保持一致
import_one model_usage_record id \
  "id,user_id,tenant_id,conversation_id,agent_task_id,model,provider,prompt_tokens,completion_tokens,total_tokens,cost_usd,latency_ms,request_type,created_at"

import_one agent_step id \
  "id,run_id,sequence,step_type,action,duration_ms,error_code,created_at"

import_one usage_event id \
  "id,tenant_id,meter,operation,request_id,window_key,amount,ref_type,ref_id,created_at"

import_one agent_task id \
  "id,request_id,user_id,conversation_id,knowledge_base_id,status,current_run_id,created_at"

# 分区注册(若走 Hive 表路径):ALTER TABLE ods_xxx ADD IF NOT EXISTS PARTITION (dt='$DT')
echo "Sqoop 全量导入完成: dt=$DT(分区注册用 ALTER TABLE ... ADD PARTITION)"
