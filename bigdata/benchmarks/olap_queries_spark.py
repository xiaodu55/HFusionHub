#!/usr/bin/env python3
"""HFusionData Analytics — OLAP 对比实验(Spark 侧)。

对 dwd_llm_call 全量明细(与 ClickHouse 同一份 HDFS Parquet 数据)执行固定
4 条分析查询,每条重复 --reps 次,打印每次的端内耗时(不含 Spark 应用启动)。
配合 run_olap_comparison.sh 的 ClickHouse 分支形成同数据跨引擎对比。

用法: spark-submit ... olap_queries_spark.py --reps 3
输出: "[olap] Q<n>,run<#>,<latency_ms>,<rows>"(由外层脚本解析落 CSV)
"""

import argparse
import sys
import time

import pyspark.sql.functions as F

from _common import WAREHOUSE, build_spark

QUERIES = {
    # Q1 租户×模型聚合
    "Q1": lambda df: (
        df.groupBy("tenant_id", "model")
        .agg(F.count(F.lit(1)).alias("cnt"),
             F.sum("total_tokens").alias("tokens"),
             F.round(F.sum("cost_usd"), 2).alias("cost"))
        .collect()),
    # Q2 日成本趋势
    "Q2": lambda df: (
        df.groupBy("event_date")
        .agg(F.round(F.sum("cost_usd"), 2).alias("cost"),
             F.round(F.avg("latency_ms"), 1).alias("avg_latency"))
        .orderBy("event_date")
        .collect()),
    # Q3 租户成本 TopN
    "Q3": lambda df: (
        df.groupBy("tenant_id")
        .agg(F.round(F.sum("cost_usd"), 2).alias("cost"))
        .orderBy(F.desc("cost"))
        .limit(5)
        .collect()),
    # Q4 按小时窗口聚合
    "Q4": lambda df: (
        df.withColumn("hour_bucket", F.date_trunc("hour", "created_at"))
        .groupBy("hour_bucket")
        .agg(F.count(F.lit(1)).alias("cnt"),
             F.round(F.avg("latency_ms"), 1).alias("avg_latency"))
        .orderBy("hour_bucket")
        .collect()),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="OLAP comparison — Spark side")
    parser.add_argument("--reps", type=int, default=3)
    args = parser.parse_args()

    spark = build_spark("hfusiondata-olap-comparison")
    spark.sparkContext.setLogLevel("WARN")
    df = spark.read.parquet(f"{WAREHOUSE}/dwd/dwd_llm_call")

    # 预热一次(首次触发 Parquet schema 推断与 YARN 执行器拉起,不计入对比)
    for qid, fn in QUERIES.items():
        fn(df)

    for qid, fn in QUERIES.items():
        for run in range(1, args.reps + 1):
            t0 = time.perf_counter()
            rows = fn(df)
            elapsed = (time.perf_counter() - t0) * 1000
            # 逗号分隔无空格:外层脚本按 IFS=, 逐列解析
            print(f"[olap],{qid},run{run},{elapsed:.0f},{len(rows)}", flush=True)

    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
