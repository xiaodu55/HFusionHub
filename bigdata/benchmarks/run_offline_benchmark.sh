#!/bin/sh
# ============================================================================
# HFusionData Analytics — 离线链路规模基准(单 dt 协议)
#
# 原理: seed --days 1 把全部合成事件压进"今天"一个 dt 分区,然后对同一分区
# 依次计时跑完整流水线(full-import → dwd → dws → quality → ads → ch-sync),
# 使"数据规模 → 作业耗时"成为单变量对比(排除日期数带来的干扰)。
# 注意: --truncate 会清空 model_usage_record/usage_event/conversation/agent_*
# 等业务表,仅用于开发/基准环境。
#
# 用法:
#   MYSQL_PASSWORD=<hfusionhub密码> ./run_offline_benchmark.sh 100000
#   ./run_offline_benchmark.sh 1000000 1 --skip-ch
#
# 产出: bigdata/benchmarks/results/offline_scale_<scale>_<时间戳>.csv
#       (stage,seconds 逐行;ods_rows 为全量导入行数) + pipeline_*.log 原始日志
# ============================================================================
set -eu

SCALE="${1:?用法: run_offline_benchmark.sh <scale> [days]}"
DAYS="${2:-1}"
SKIP_CH="${3:-}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RESULT_DIR="$REPO_ROOT/bigdata/benchmarks/results"
mkdir -p "$RESULT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$RESULT_DIR/offline_scale_${SCALE}_${STAMP}.csv"
LOG="$RESULT_DIR/pipeline_${SCALE}_${STAMP}.log"

# MySQL 凭据: 优先环境变量,否则从 docker/.env 读取
if [ -z "${MYSQL_PASSWORD:-}" ]; then
  MYSQL_PASSWORD="$(grep '^MYSQL_PASSWORD=' "$REPO_ROOT/docker/.env" | cut -d= -f2)"
fi

# Spark-on-YARN 提交器(analytics-spark 容器)。client 模式必须显式
# spark.driver.host/bindAddress,否则 YARN 执行器回连双网卡容器上的 driver 被拒;
# clickhouse 驱动必须进 --driver-class-path(DriverManager 用系统类加载器,
# 不读 --jars)。
submit() { # $1=容器内脚本路径(相对 /opt/bigdata) 其余=脚本参数
  script="$1"; shift
  docker exec analytics-spark sh -c "export PATH=/opt/spark/bin:\$PATH; \
    spark-submit --master yarn \
    --conf spark.driver.host=analytics-spark --conf spark.driver.bindAddress=0.0.0.0 \
    --driver-class-path /opt/bigdata/jars/clickhouse-jdbc-0.6.3-all.jar \
    --jars /opt/bigdata/jars/clickhouse-jdbc-0.6.3-all.jar,/opt/bigdata/jars/mysql-connector-j-8.0.33.jar \
    /opt/bigdata/$script $*"
}

now() { date +%s; }

timed() { # $1=阶段名 其余=命令;秒数追加进 CSV,输出并入 pipeline 日志
  stage="$1"; shift
  t0=$(now)
  if ! "$@" >> "$LOG" 2>&1; then
    echo "  [$stage] FAILED(详见 $(basename "$LOG"))" >&2
    exit 1
  fi
  t1=$(now)
  echo "$stage,$((t1 - t0))" >> "$OUT"
  echo "  [$stage] $((t1 - t0))s"
}

echo "stage,seconds" > "$OUT"
echo "== 离线基准 scale=$SCALE days=$DAYS =="

# ── 1) 造数(清库 + 单日全量事件) ────────────────────────────────────────────
t0=$(now)
python "$REPO_ROOT/bigdata/scripts/seed_generator.py" --truncate \
  --scale "$SCALE" --days "$DAYS" --user hfusionhub --password "$MYSQL_PASSWORD" \
  > "$RESULT_DIR/seed_${SCALE}_${STAMP}.log" 2>&1
t1=$(now)
echo "seed,$((t1 - t0))" >> "$OUT"
echo "  [seed] $((t1 - t0))s"

# ── 2) 以 MySQL 实际最大事件日期为基准 dt(不依赖本地时区/星期推断) ─────────
DT=$(python - "$MYSQL_PASSWORD" <<'PYEOF'
import os, pymysql
conn = pymysql.connect(host="127.0.0.1", port=3306, user="hfusionhub",
                       password=os.sys.argv[1], database="hfusionhub")
cur = conn.cursor()
cur.execute("SELECT DATE(MAX(created_at)) FROM model_usage_record")
print(cur.fetchone()[0])
PYEOF
)
echo "dt,$DT" >> "$OUT"
echo "  [dt] $DT"

# ── 3) 流水线整链计时 ──────────────────────────────────────────────────────
timed full-import   submit scripts/full_import.py   --dt "$DT"
timed dwd-transform submit spark-jobs/dwd_transform.py --dt "$DT"
timed dws-aggregate submit spark-jobs/dws_aggregate.py --dt "$DT"
timed quality-check submit spark-jobs/quality_check.py --dt "$DT"
timed ads-build     submit spark-jobs/ads_build.py --dt "$DT"

# ── 4) ODS 行数(full_import 的 [ok] 行汇总) ────────────────────────────────
ODS_ROWS=$(grep -oE "rows=[0-9]+" "$LOG" | cut -d= -f2 | awk '{s+=$1} END {print s+0}')
echo "ods_rows,$ODS_ROWS" >> "$OUT"
echo "  [ods_rows] $ODS_ROWS"

# ── 5) 可选: 同步 ClickHouse(标准档) ────────────────────────────────────────
if [ "$SKIP_CH" != "--skip-ch" ]; then
  timed ch-sync submit spark-jobs/ch_sync.py
fi

echo "== 完成: $OUT =="
cat "$OUT"
