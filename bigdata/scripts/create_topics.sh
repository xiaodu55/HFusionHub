#!/usr/bin/env bash
# ============================================================================
# HFusionData Analytics — Kafka topic 初始化(幂等,重复执行安全)
# 用法: 在 hadoop-client 或任意能连 analytics-kafka:9092 的容器内执行
#   bash /opt/bigdata/scripts/create_topics.sh
# ============================================================================
set -euo pipefail

BROKER="${BROKER:-analytics-kafka:9092}"

TOPICS=(
  "ods_model_usage_record:6"
  "ods_agent_step:6"
  "ods_usage_event:6"
  "ods_agent_task:6"
)

for spec in "${TOPICS[@]}"; do
  topic="${spec%%:*}"
  parts="${spec##*:}"
  if kafka-topics.sh --bootstrap-server "$BROKER" --list | grep -qx "$topic"; then
    echo "[skip] topic $topic 已存在"
  else
    kafka-topics.sh --bootstrap-server "$BROKER" \
      --create --topic "$topic" \
      --partitions "$parts" --replication-factor 1 \
      --config retention.ms=604800000      # 7 天(增量 ODS 落 HDFS 后即可过期)
    echo "[ok] topic $topic 已创建($parts 分区)"
  fi
done
echo "Kafka topics 初始化完成"
