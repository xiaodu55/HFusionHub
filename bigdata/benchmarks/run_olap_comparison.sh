#!/bin/sh
# ============================================================================
# HFusionData Analytics — OLAP 对比实验执行器
#
# 同一份 dwd_llm_call 数据(单 dt 协议,约 100 万级明细)在多引擎上执行固定
# 4 条分析查询(Q1 租户×模型聚合 / Q2 日趋势 / Q3 TopN / Q4 小时窗口),
# 每条 3 次,记录端内延迟。
#
# 引擎:
#   clickhouse — HTTP 接口直查 analytics.dwd_llm_call(本地列存)
#   spark      — YARN PySpark 扫 HDFS Parquet(计算存储解耦口径)
#   hive       — HiveServer2 JDBC(已知 Tez 引擎不可用,预期 N/A,如实记录)
#
# 产出: bigdata/benchmarks/results/olap_comparison_<时间戳>.csv
# ============================================================================
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RESULT_DIR="$REPO_ROOT/bigdata/benchmarks/results"
mkdir -p "$RESULT_DIR"
OUT="$RESULT_DIR/olap_comparison_$(date +%Y%m%d-%H%M%S).csv"
CH_USER="${CH_USER:-analytics}"
CH_PASSWORD="${CH_PASSWORD:-analytics123}"
REPS=3

echo "engine,query,run,latency_ms,rows" > "$OUT"

CH_SQL[1]="SELECT tenant_id, model, count() AS cnt, sum(total_tokens) AS tokens, round(sum(cost_usd),2) AS cost FROM analytics.dwd_llm_call GROUP BY tenant_id, model FORMAT TSV"
CH_SQL[2]="SELECT event_date, round(sum(cost_usd),2) AS cost, round(avg(latency_ms),1) AS avg_latency FROM analytics.dwd_llm_call GROUP BY event_date ORDER BY event_date FORMAT TSV"
CH_SQL[3]="SELECT tenant_id, round(sum(cost_usd),2) AS cost FROM analytics.dwd_llm_call GROUP BY tenant_id ORDER BY cost DESC LIMIT 5 FORMAT TSV"
CH_SQL[4]="SELECT toStartOfHour(created_at) AS h, count() AS cnt, round(avg(latency_ms),1) AS avg_latency FROM analytics.dwd_llm_call GROUP BY h ORDER BY h FORMAT TSV"

echo "== ClickHouse(本地列存) =="
for q in 1 2 3 4; do
  for run in 1 2 3; do
    line=$(curl -s -m 60 --user "$CH_USER:$CH_PASSWORD" "http://localhost:18123/" \
      --data "${CH_SQL[$q]}" \
      -w "%{time_total}" -o /tmp/olap_rows.txt)
    ms=$(awk -v t="$line" 'BEGIN {printf "%.0f", t * 1000}')
    rows=$(grep -c . /tmp/olap_rows.txt 2>/dev/null || echo 0)
    echo "clickhouse,Q$q,$run,$ms,$rows" >> "$OUT"
    echo "  [clickhouse Q$q run$run] ${ms}ms (${rows} 行)"
  done
done

echo "== Spark SQL(YARN 扫 HDFS Parquet) =="
docker exec analytics-spark sh -c "export PATH=/opt/spark/bin:\$PATH; \
  spark-submit --master yarn \
  --conf spark.driver.host=analytics-spark --conf spark.driver.bindAddress=0.0.0.0 \
  --py-files /opt/bigdata/spark-jobs/_common.py \
  /opt/bigdata/benchmarks/olap_queries_spark.py --reps $REPS" 2>&1 |
  grep "^\[olap\]" | while IFS=, read -r _tag q run ms rows; do
    echo "spark,$q,$run,$ms,$rows" >> "$OUT"
    echo "  [spark $q $run] ${ms}ms (${rows} 行)"
  done

echo "== Hive(HiveServer2 + Tez,已知不可用,如实记录) =="
if docker exec hive-server2 sh -c "timeout 120 beeline -u jdbc:hive2://localhost:10000 -n hive \
    -e 'SELECT count(*) FROM hfusionhub.dwd_llm_call'" >> "$OUT.hive" 2>&1; then
  echo "hive,Q1,1,ok," >> "$OUT"
  echo "  [hive] 可用"
else
  echo "hive,Q1,1,N/A(Tez 计算引擎不可用,见 docs/BIGDATA_ARCHITECTURE.md 踩坑 #6;生产口径为 Spark 计算引擎)" >> "$OUT"
  echo "  [hive] Tez 不可用 → N/A(如实记录)"
fi
rm -f "$OUT.hive"

echo "== 完成: $OUT =="
cat "$OUT"
