#!/usr/bin/env python3
"""HFusionData Analytics — MySQL 全量批量导入 HDFS ODS(Spark JDBC)。

定位:Sqoop/DataX 的现代等价物——Spark JDBC 并行分区读取 MySQL 业务表,
按 dt(数据日期)分区写 HDFS Parquet。既可由 BigDataBatchScheduler 每日
触发,也可人工对任意历史 dt 回补(幂等:INSERT OVERWRITE 该分区)。

用法(在 hadoop-client 容器或任一装了 spark 的环境):
  spark-submit --master yarn --deploy-mode client \\
    --jars /opt/bigdata/jars/mysql-connector-j-8.0.33.jar \\
    /opt/bigdata/scripts/full_import.py \\
    --dt 2026-08-30 \\
    --tables model_usage_record,agent_step,usage_event,agent_task

主键列决定 JDBC 并行度分区列;分区数 = min(numPartitions, 该表主键跨度)。
"""

import argparse
import datetime as _dt

from pyspark.sql import SparkSession

# 表 → JDBC 并行分区主键(必须为数值列;与 java-backend 迁移脚本一致)
# 注意: agent_task / agent_step 无 tenant_id 列,租户维度在 DWD 层经
# dim_user(user_id -> tenant_id)回补,与 Java 侧 resolveRunTenant 语义一致。
TABLE_PARTITIONS = {
    "model_usage_record": "id",
    "agent_step": "id",
    "usage_event": "id",
    "agent_task": "id",
    "agent_run": "id",
    "sys_user": "id",
}

ODS_ROOT = "/warehouse/hfusionhub/ods"

# 各表需携带的租户/时间列(与 MySQL schema 对齐;agent_step 无 tenant_id,
# 由 DWD 层经 agent_run 维表回补)
TABLE_COLUMNS = {
    "model_usage_record": [
        "id", "user_id", "tenant_id", "conversation_id", "agent_task_id",
        "model", "provider", "prompt_tokens", "completion_tokens",
        "total_tokens", "cost_usd", "latency_ms", "request_type", "created_at",
    ],
    "agent_step": [
        "id", "run_id", "sequence", "step_type", "action",
        "duration_ms", "error_code", "created_at",
    ],
    "usage_event": [
        "id", "tenant_id", "meter", "operation", "request_id",
        "window_key", "amount", "ref_type", "ref_id", "created_at",
    ],
    "agent_task": [
        "id", "request_id", "user_id", "conversation_id", "knowledge_base_id",
        "status", "current_run_id", "created_at",
    ],
    "agent_run": [
        "id", "task_id", "run_uuid", "attempt_number", "tenant_id", "status",
        "model", "tool_calls_count", "error_code", "failed_tool",
        "duration_ms", "created_at",
    ],
    # 仅导分析所需列;password/phone/email 等敏感字段不进数仓(脱敏边界)
    "sys_user": [
        "id", "username", "tenant_id", "role", "status", "created_at",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MySQL -> HDFS ODS full import")
    parser.add_argument("--dt", required=False,
                        default=_dt.date.today().isoformat(),
                        help="数据日期分区(YYYY-MM-DD),默认今天;回补传历史日期")
    parser.add_argument("--tables", required=False,
                        default=",".join(TABLE_PARTITIONS.keys()),
                        help="逗号分隔的表清单")
    parser.add_argument("--num-partitions", type=int, default=4,
                        help="JDBC 并行读取分区数")
    parser.add_argument("--fetchsize", type=int, default=10000)
    return parser.parse_args()


def build_spark() -> SparkSession:
    return (
        SparkSession.builder
        .appName("HFusionData-FullImport")
        # on YARN 提交时由 spark-submit 参数指定 master;local 调试去掉该行亦可
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.sessionState.createHive", "false")  # 计算存储解耦,不碰 metastore
        .getOrCreate()
    )


def import_table(spark: SparkSession, table: str, dt: str,
                 jdbc_url: str, db_user: str, db_password: str,
                 num_partitions: int, fetchsize: int) -> int:
    pk = TABLE_PARTITIONS[table]
    cols = ", ".join(TABLE_COLUMNS[table])

    # 预读主键上界(JDBC partitionColumn 必须同时提供 lowerBound/upperBound)
    upper_bound = max(1, int(
        spark.read.format("jdbc")
        .option("url", jdbc_url)
        .option("query", f"SELECT COALESCE(MAX({pk}), 0) AS hi FROM {table}")
        .option("user", db_user)
        .option("password", db_password)
        .option("driver", "com.mysql.cj.jdbc.Driver")
        .load()
        .collect()[0]["hi"]
    ) + 1)

    reader = (
        spark.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", f"(SELECT {cols} FROM {table}) t")
        .option("user", db_user)
        .option("password", db_password)
        .option("driver", "com.mysql.cj.jdbc.Driver")
        .option("fetchsize", fetchsize)
        .option("partitionColumn", pk)
        .option("lowerBound", "1")
        .option("upperBound", str(upper_bound))
        .option("numPartitions", str(num_partitions))
    )

    df = reader.load()
    # dt 由导入日期决定(以 created_at 过滤的上界由调度器保证;全量快照幂等)
    df = df.withColumn("dt", __import__("pyspark").sql.functions.lit(dt))
    out_path = f"{ODS_ROOT}/{table}"
    (
        df.write.mode("overwrite")
        .partitionBy("dt")
        .parquet(out_path)
    )
    count = df.count()
    print(f"[ok] {table} -> {out_path} dt={dt} rows={count}")
    return count


def main() -> None:
    args = parse_args()
    import os
    jdbc_url = os.environ.get(
        "ANALYTICS_JDBC_URL", "jdbc:mysql://mysql8:3306/hfusionhub?useSSL=false&allowPublicKeyRetrieval=true")
    db_user = os.environ.get("ANALYTICS_DB_USER", "hfusionhub")
    db_password = os.environ.get("ANALYTICS_DB_PASSWORD", "")

    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")
    total = 0
    for table in [t.strip() for t in args.tables.split(",") if t.strip()]:
        if table not in TABLE_PARTITIONS:
            print(f"[skip] 未知表 {table}(不在 TABLE_PARTITIONS 清单)")
            continue
        total += import_table(spark, table, args.dt, jdbc_url,
                              db_user, db_password,
                              args.num_partitions, args.fetchsize)
    print(f"[done] 全量导入完成,共 {total} 行,dt={args.dt}")
    spark.stop()


if __name__ == "__main__":
    main()
