#!/usr/bin/env python3
"""HFusionData Analytics — ClickHouse 同步作业(标准档)。

标准档(analytics-full)的 OLAP 引擎补齐:把 Spark/Hive 侧计算结果落到
ClickHouse,供大屏高频查询降载与 OLAP 对比实验。三个目标表:

- analytics.dwd_llm_call           ← HDFS Parquet(dwd/dwd_llm_call 明细)
- analytics.ads_tenant_model_daily ← HDFS Parquet(dws/dws_tenant_model_daily)
- analytics.realtime_metrics       ← MySQL V82(Flink 直写 MySQL 为准,CH 为只读镜像)

幂等:写入前 TRUNCATE 目标表再 append(ReplacingMergeTree 兜底去重),
与上游 dt 分区覆盖写语义一致——重复执行安全,可任意回补。
精简档不部署 ClickHouse:Pipeline 步骤模板未配置时该步自动 SKIPPED。

用法: spark-submit --master yarn --jars clickhouse-jdbc-0.6.3-all.jar,mysql-connector-j-8.0.33.jar \\
        ch_sync.py [--skip-realtime]
"""

import argparse
import os
import time

import pyspark.sql.functions as F

from _common import build_spark, mysql_options, WAREHOUSE

CH_URL = os.environ.get("CH_JDBC_URL", "jdbc:clickhouse://clickhouse:8123/analytics")
CH_DRIVER = "com.clickhouse.jdbc.ClickHouseDriver"
CH_USER = os.environ.get("CH_USER", "analytics")
CH_PASSWORD = os.environ.get("CH_PASSWORD", "analytics123")
CH_BATCH_SIZE = int(os.environ.get("CH_BATCH_SIZE", "100000"))


def ch_write_options():
    return {
        "url": CH_URL,
        "driver": CH_DRIVER,
        "user": CH_USER,
        "password": CH_PASSWORD,
        "batchsize": str(CH_BATCH_SIZE),
        "isolationLevel": "NONE",
    }


def ch_truncate(spark, table: str) -> None:
    """写入前清空目标表(走 JVM DriverManager,避免 Spark overwrite 触发
    DROP/CREATE 破坏 ReplacingMergeTree + MATERIALIZED 列定义)。"""
    jvm = spark._sc._jvm
    conn = jvm.java.sql.DriverManager.getConnection(CH_URL, CH_USER, CH_PASSWORD)
    try:
        stmt = conn.createStatement()
        try:
            stmt.execute(f"TRUNCATE TABLE {table}")
        finally:
            stmt.close()
    finally:
        conn.close()


def sync_df(spark, df, table: str) -> tuple:
    t0 = time.time()
    count = df.count()
    ch_truncate(spark, table)
    (
        df.write.format("jdbc")
        .options(**ch_write_options())
        .option("dbtable", table)
        .mode("append")
        .save()
    )
    elapsed = time.time() - t0
    throughput = count / elapsed if elapsed > 0 else 0
    print(f"[ch-sync] {table}: {count} rows in {elapsed:.1f}s ({throughput:,.0f} rows/s)")
    return count, elapsed


def sync_dwd_llm_call(spark) -> tuple:
    df = (
        spark.read.parquet(f"{WAREHOUSE}/dwd/dwd_llm_call")
        .select(
            "dt",
            "tenant_id",
            "user_id",
            "conversation_id",
            "agent_task_id",
            "model",
            "provider",
            "request_type",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost_usd",
            "latency_ms",
            "created_at",
            F.to_date("event_date").alias("event_date"),
        )
    )
    return sync_df(spark, df, "analytics.dwd_llm_call")


def sync_ads_tenant_model_daily(spark) -> tuple:
    df = (
        spark.read.parquet(f"{WAREHOUSE}/dws/dws_tenant_model_daily")
        .select(
            F.to_date("stat_date").alias("stat_date"),
            "tenant_id",
            "model",
            "call_count",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost_usd",
            "avg_latency_ms",
            "p95_latency_ms",
        )
    )
    return sync_df(spark, df, "analytics.ads_tenant_model_daily")


def sync_realtime_metrics(spark) -> tuple:
    df = (
        spark.read.format("jdbc")
        .options(**mysql_options())
        .option("dbtable", "analytics_realtime_metrics")
        .load()
        .select(
            "window_start",
            "window_end",
            "tenant_id",
            "model",
            "request_count",
            "total_tokens",
            "total_cost",
            "avg_latency_ms",
            "max_latency_ms",
        )
    )
    return sync_df(spark, df, "analytics.realtime_metrics")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync warehouse results into ClickHouse")
    parser.add_argument("--skip-realtime", action="store_true",
                        help="跳过 MySQL realtime_metrics 镜像(仅同步 HDFS 侧)")
    args = parser.parse_args()

    spark = build_spark("hfusiondata-ch-sync")
    started = time.time()
    summary = {}

    summary["dwd_llm_call"] = sync_dwd_llm_call(spark)
    summary["ads_tenant_model_daily"] = sync_ads_tenant_model_daily(spark)
    if not args.skip_realtime:
        summary["realtime_metrics"] = sync_realtime_metrics(spark)

    total = time.time() - started
    for table, (rows, seconds) in summary.items():
        print(f"[ch-sync] RESULT {table} rows={rows} seconds={seconds:.1f}")
    print(f"[ch-sync] RESULT total_seconds={total:.1f} tables={len(summary)}")

    spark.stop()
    return 0


if __name__ == "__main__":
    sys_exit = main()
    raise SystemExit(sys_exit)
