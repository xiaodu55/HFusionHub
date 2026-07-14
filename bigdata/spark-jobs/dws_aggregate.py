#!/usr/bin/env python3
"""HFusionData Analytics — DWS 汇总层构建。

输入: DWD(dt 分区) 输出: 4 张 DWS(dt 分区)
口径与 hive-sql/05_dws.sql 声明一致;stat_date 取 event_date(事件真实日期),
因此对同一 dt 分区重跑/回补会重算该批数据涉及的所有事件日,聚合结果幂等。

用法: spark-submit --master yarn dws_aggregate.py --dt 2026-08-30
"""

import argparse

import pyspark.sql.functions as F

from _common import build_spark, read_ods, write_partitioned, WAREHOUSE
import os


def read_dwd(spark, table: str, dt: str):
    return spark.read.parquet(f"{WAREHOUSE}/dwd/{table}").where(f"dt = '{dt}'").drop("dt")


def p95(value_col: str) -> "Column":
    return F.percentile_approx(value_col, 0.95, 10000)


def build_dws(spark, dt: str) -> dict:
    stats = {}

    calls = read_dwd(spark, "dwd_llm_call", dt)
    # ── dws_tenant_model_daily ─────────────────────────────────────────────
    tenant_model = (
        calls.withColumn("stat_date", F.col("event_date"))
        .groupBy("tenant_id", "model", "stat_date")
        .agg(
            F.count("*").alias("call_count"),
            F.sum("prompt_tokens").alias("prompt_tokens"),
            F.sum("completion_tokens").alias("completion_tokens"),
            F.sum("total_tokens").alias("total_tokens"),
            F.sum("cost_usd").alias("cost_usd"),
            F.avg("latency_ms").cast("bigint").alias("avg_latency_ms"),
            p95("latency_ms").cast("bigint").alias("p95_latency_ms"),
        )
    )
    stats["dws_tenant_model_daily"] = write_partitioned(
        tenant_model, "dws", "dws_tenant_model_daily", dt)

    # ── dws_tenant_step_daily ───────────────────────────────────────────────
    steps = read_dwd(spark, "dwd_agent_step", dt)
    tenant_step = (
        steps.withColumn("stat_date", F.col("event_date"))
        .groupBy("tenant_id", "step_type", "stat_date")
        .agg(
            F.count("*").alias("step_count"),
            F.sum(F.when(F.col("is_error"), 1).otherwise(0)).alias("error_count"),
            F.round(
                F.sum(F.when(F.col("is_error"), 1).otherwise(0)) / F.count("*"), 6
            ).alias("error_rate"),
            F.avg("duration_ms").cast("bigint").alias("avg_duration_ms"),
        )
    )
    stats["dws_tenant_step_daily"] = write_partitioned(
        tenant_step, "dws", "dws_tenant_step_daily", dt)

    # ── dws_tenant_meter_daily ──────────────────────────────────────────────
    usage = read_dwd(spark, "dwd_usage_event", dt)
    tenant_meter = (
        usage.withColumn("stat_date", F.col("event_date"))
        .groupBy("tenant_id", "meter", "stat_date")
        .agg(
            F.sum(F.when(F.col("operation") == "RESERVE", F.col("amount")).otherwise(0))
            .alias("reserve_amount"),
            F.sum(F.when(F.col("operation") == "COMMIT", F.col("amount")).otherwise(0))
            .alias("commit_amount"),
            F.sum(F.when(F.col("operation") == "RELEASE", F.col("amount")).otherwise(0))
            .alias("release_amount"),
            F.count("*").alias("event_count"),
        )
    )
    stats["dws_tenant_meter_daily"] = write_partitioned(
        tenant_meter, "dws", "dws_tenant_meter_daily", dt)

    # ── dws_model_daily(平台口径) ──────────────────────────────────────────
    model_daily = (
        calls.withColumn("stat_date", F.col("event_date"))
        .groupBy("model", "stat_date")
        .agg(
            F.count("*").alias("call_count"),
            F.sum("total_tokens").alias("total_tokens"),
            F.sum("cost_usd").alias("cost_usd"),
            F.avg("latency_ms").cast("bigint").alias("avg_latency_ms"),
            p95("latency_ms").cast("bigint").alias("p95_latency_ms"),
        )
    )
    stats["dws_model_daily"] = write_partitioned(model_daily, "dws", "dws_model_daily", dt)

    return stats


def main():
    parser = argparse.ArgumentParser(description="DWD -> DWS aggregate")
    parser.add_argument("--dt", required=True)
    args = parser.parse_args()

    spark = build_spark("HFusionData-DWS")
    spark.sparkContext.setLogLevel("WARN")
    stats = build_dws(spark, args.dt)
    for name, path in stats.items():
        print(f"[ok] {name} -> {path} (dt={args.dt})")
    spark.stop()


if __name__ == "__main__":
    main()
