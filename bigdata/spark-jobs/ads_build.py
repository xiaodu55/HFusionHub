#!/usr/bin/env python3
"""HFusionData Analytics — ADS 应用层构建 + MySQL 同构回写。

输入: DWS/DWD   输出: 5 张 ADS(Hive 侧 Parquet)+ MySQL ads_*(V82 建表)
大屏与 Superset 读 Hive/ClickHouse;Java AnalyticsController 读 MySQL 镜像
(业务侧零 Hadoop 依赖)。tenant_id = -1 表示平台全局口径。

用法: spark-submit --master yarn --jars mysql-connector-j-8.0.33.jar \\
        ads_build.py --dt 2026-08-30 [--mysql-mirror true]
"""

import argparse
import os

import pyspark.sql.functions as F
from pyspark.sql import Window

from _common import build_spark, WAREHOUSE, write_mysql_mirror


def read_layer(spark, layer: str, table: str, dt: str):
    return spark.read.parquet(f"{WAREHOUSE}/{layer}/{table}").where(f"dt = '{dt}'").drop("dt")


def build_ads(spark, dt: str) -> dict:
    stats = {}

    tenant_model = read_layer(spark, "dws", "dws_tenant_model_daily", dt)
    model_daily = read_layer(spark, "dws", "dws_model_daily", dt)
    tenant_step = read_layer(spark, "dws", "dws_tenant_step_daily", dt)
    evals = read_layer(spark, "dwd", "dwd_eval_record", dt)

    # ── ads_cost_daily(租户 + 平台全局=-1) ─────────────────────────────────
    per_tenant = (
        tenant_model.groupBy("tenant_id", "stat_date")
        .agg(
            F.sum("call_count").alias("call_count"),
            F.sum("total_tokens").alias("total_tokens"),
            F.sum("cost_usd").alias("cost_usd"),
        )
    )
    # 月费外推: 当月已发生成本 / 已过天数 * 当月天数
    per_tenant = per_tenant.withColumn(
        "day_of_month", F.dayofmonth(F.to_date("stat_date")))
    w_month = Window.partitionBy("tenant_id", F.substring("stat_date", 1, 7))
    per_tenant = (
        per_tenant.withColumn("month_cost", F.sum("cost_usd").over(w_month))
        .withColumn("max_day", F.max("day_of_month").over(w_month))
        .withColumn(
            "est_month_cost",
            F.round(
                F.col("month_cost") / F.col("max_day") * F.lit(30), 2))
        .select("tenant_id", "stat_date", "call_count", "total_tokens",
                "cost_usd", "est_month_cost")
    )
    platform = (
        model_daily.groupBy("stat_date")
        .agg(
            F.sum("call_count").alias("call_count"),
            F.sum("total_tokens").alias("total_tokens"),
            F.sum("cost_usd").alias("cost_usd"),
        )
        .withColumn("tenant_id", F.lit(-1).cast("bigint"))
        .withColumn("est_month_cost", F.lit(None).cast("decimal(12,2)"))
        .select("tenant_id", "stat_date", "call_count", "total_tokens",
                "cost_usd", "est_month_cost")
    )
    cost_daily = per_tenant.unionByName(platform)
    stats["ads_cost_daily"] = write_partitioned(cost_daily, "ads", "ads_cost_daily", dt)

    # ── ads_model_share(按租户 + 平台) ─────────────────────────────────────
    w_share = Window.partitionBy("tenant_id", "stat_date")
    model_share = (
        tenant_model.withColumn(
            "cost_share",
            F.round(F.col("cost_usd") / F.sum("cost_usd").over(w_share), 6))
        .where(F.col("cost_share").isNotNull())
        .select("tenant_id", "model", "stat_date", "call_count", "cost_usd", "cost_share")
    )
    platform_share = (
        model_daily.withColumn("tenant_id", F.lit(-1).cast("bigint"))
        .withColumn(
            "cost_share",
            F.round(F.col("cost_usd") / F.sum("cost_usd").over(w_share), 6))
        .select("tenant_id", "model", "stat_date", "call_count", "cost_usd", "cost_share")
    )
    share = model_share.unionByName(platform_share)
    stats["ads_model_share"] = write_partitioned(share, "ads", "ads_model_share", dt)

    # ── ads_tenant_topn(平台管理员视图,Top 20) ────────────────────────────
    w_rank = Window.partitionBy("stat_date").orderBy(F.desc("cost_usd"))
    topn = (
        per_tenant.where(F.col("tenant_id") > 0)
        .withColumn("rank_no", F.row_number().over(w_rank))
        .where(F.col("rank_no") <= 20)
        .select("stat_date", "rank_no", "tenant_id", "call_count", "total_tokens", "cost_usd")
    )
    stats["ads_tenant_topn"] = write_partitioned(topn, "ads", "ads_tenant_topn", dt)

    # ── ads_tool_success(近 7 天滚动,按 stat_date 汇总到当日) ─────────────
    # 精简实现: 仅聚合当日;7 天滚动由查询端 SUM(ADS 分区) 完成,口径写入文档
    tool = (
        tenant_step.withColumnRenamed("stat_date", "stat_date")
        .withColumnRenamed("error_rate", "err")
        .select(
            "tenant_id", "step_type", "stat_date", "step_count", "error_count",
            F.round(1 - F.col("err"), 6).alias("success_rate"))
    )
    stats["ads_tool_success"] = write_partitioned(tool, "ads", "ads_tool_success", dt)

    # ── ads_eval_quality(评测链路;归属租户经 dataset 缺失按平台 -1 口径) ───
    eval_quality = (
        evals.withColumn("stat_date", F.col("event_date"))
        .groupBy("stat_date")
        .agg(
            F.count("*").alias("eval_count"),
            F.round(F.avg("hit_ratio"), 6).alias("avg_hit_ratio"),
            F.avg("ttft_ms").cast("bigint").alias("avg_ttft_ms"),
            F.avg("latency_ms").cast("bigint").alias("avg_latency_ms"),
            F.round(
                F.sum(F.when(F.col("final_status") != "completed", 1).otherwise(0))
                / F.count("*"), 6).alias("failure_rate"),
        )
        .withColumn("tenant_id", F.lit(-1).cast("bigint"))
        .select("tenant_id", "stat_date", "eval_count", "avg_hit_ratio",
                "avg_ttft_ms", "avg_latency_ms", "failure_rate")
    )
    stats["ads_eval_quality"] = write_partitioned(eval_quality, "ads", "ads_eval_quality", dt)

    return stats


def main():
    parser = argparse.ArgumentParser(description="DWS/DWD -> ADS + MySQL mirror")
    parser.add_argument("--dt", required=True)
    parser.add_argument("--mysql-mirror", default="true",
                        help="是否回写 MySQL ads_*(精简环境可 false)")
    args = parser.parse_args()

    spark = build_spark("HFusionData-ADS")
    spark.sparkContext.setLogLevel("WARN")
    stats = build_ads(spark, args.dt)
    for name, path in stats.items():
        print(f"[ok] {name} -> {path} (dt={args.dt})")

    if str(args.mysql_mirror).lower() == "true":
        if not os.environ.get("ANALYTICS_DB_PASSWORD"):
            print("[warn] 未设置 ANALYTICS_DB_PASSWORD,跳过 MySQL 回写")
        else:
            # 全表刷新语义:从 Hive ADS 全分区读取(聚合小表),整表覆盖 MySQL,
            # 与单日回补天然幂等,详见 _common.write_mysql_mirror
            for table in ("ads_cost_daily", "ads_model_share", "ads_tenant_topn",
                          "ads_tool_success", "ads_eval_quality"):
                df = spark.read.parquet(f"{WAREHOUSE}/ads/{table}")
                write_mysql_mirror(df, table, args.dt)

    spark.stop()


if __name__ == "__main__":
    main()
