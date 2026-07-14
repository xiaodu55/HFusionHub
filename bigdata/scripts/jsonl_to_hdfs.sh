#!/usr/bin/env bash
# ============================================================================
# HFusionData Analytics — Python 评测 JSONL 入 HDFS ODS
# 把 python-ai/data/eval_harness/runs/*.jsonl 按运行批次放入
# HDFS /warehouse/hfusionhub/ods/eval_record/dt=<运行日期>/(JSON 格式,
# Hive 侧 ods_eval_record 用 JsonSerDe 读取;仅追加,不做转换——转换属 DWD)
#
# 用法: bash /opt/bigdata/scripts/jsonl_to_hdfs.sh [宿主机或容器内源目录]
# ============================================================================
set -euo pipefail

SRC_DIR="${1:-/opt/bigdata/incoming/eval_runs}"
DT="${2:-$(date +%F)}"
TARGET="/warehouse/hfusionhub/ods/eval_record/dt=${DT}"

if [ ! -d "$SRC_DIR" ] || [ -z "$(ls -A "$SRC_DIR" 2>/dev/null)" ]; then
  echo "[warn] 源目录 $SRC_DIR 为空,跳过"
  exit 0
fi

hdfs dfs -mkdir -p "$TARGET"
for f in "$SRC_DIR"/*.jsonl; do
  [ -f "$f" ] || continue
  # 追加语义:同一文件重传会重复,文件名含运行时间戳因此天然幂等
  hdfs dfs -put -f "$f" "$TARGET/"
  echo "[ok] $(basename "$f") -> $TARGET"
done

hdfs dfs -chmod -R 755 "$(dirname "$TARGET")"
echo "评测 JSONL 入湖完成: $TARGET"
