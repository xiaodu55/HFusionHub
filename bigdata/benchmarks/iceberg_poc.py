#!/usr/bin/env python3
"""HFusionData Analytics — Iceberg 湖表 PoC + 对比实验。

对比两种"更新"写法在同一份数据(dwd_llm_call 明细,~80 万行)上的耗时:
  A. 现状口径: dt 分区整体重写(INSERT OVERWRITE ... SELECT)
  B. Iceberg:  MERGE INTO 行级更新(仅写变更数据文件)
并演示 time-travel(VERSION AS OF)与 schema evolution(ADD COLUMN)。

用法: spark-submit --master yarn --conf spark.driver.host=... \
        --conf spark.driver.bindAddress=0.0.0.0 \
        --driver-class-path <iceberg jar> --jars <iceberg jar> \
        iceberg_poc.py --reps 2
输出: "[poc] stage=<x> rows=<n> seconds=<t>"(外层解析落 CSV)
"""

import argparse
import json
import time

from pyspark.sql import SparkSession, functions as F


def timed(label, fn):
    t0 = time.perf_counter()
    result = fn()
    seconds = time.perf_counter() - t0
    rows = result.count() if hasattr(result, "count") else -1
    print(f"[poc] stage={label} rows={rows} seconds={seconds:.1f}", flush=True)
    return seconds, rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Iceberg PoC + comparison")
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--sample-rate", type=float, default=0.01,
                        help="MERGE 更新行占比")
    args = parser.parse_args()

    spark = (SparkSession.builder.appName("hfusiondata-iceberg-poc")
             .config("spark.sql.extensions",
                     "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
             .config("spark.sql.catalog.hf_ice", "org.apache.iceberg.spark.SparkCatalog")
             .config("spark.sql.catalog.hf_ice.type", "hadoop")
             .config("spark.sql.catalog.hf_ice.warehouse",
                     "hdfs:///warehouse/hfusionhub-iceberg")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")

    src = spark.read.parquet("/warehouse/hfusionhub/dwd/dwd_llm_call")
    base = (src.withColumn("row_id", F.xxhash64(F.col("tenant_id"), F.col("model"), F.col("created_at"), F.col("prompt_tokens"), F.col("total_tokens"), F.col("cost_usd")))
               .withColumn("event_date", F.to_date("event_date")))

    # ── 初始装载(Iceberg 建表 + 全量写入) ─────────────────────────────────
    spark.sql("DROP TABLE IF EXISTS hf_ice.dwd.dwd_llm_call_poc")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS hf_ice.dwd")

    t0 = time.perf_counter()
    (base.writeTo("hf_ice.dwd.dwd_llm_call_poc")
         .using("iceberg")
         .partitionedBy("event_date")
         .create())
    init_seconds = time.perf_counter() - t0
    init_rows = spark.table("hf_ice.dwd.dwd_llm_call_poc").count()
    print(f"[poc] stage=iceberg-init rows={init_rows} seconds={init_seconds:.1f}", flush=True)

    snapshots = spark.sql(
        "SELECT snapshot_id FROM hf_ice.dwd.dwd_llm_call_poc.snapshots ORDER BY committed_at"
    ).collect()
    init_snapshot = snapshots[-1]["snapshot_id"]

    # ── 对比实验: 覆盖写 vs MERGE 行级更新 ────────────────────────────────
    # 更新集: 采样 1% 行,模拟"延迟修正"(latency_ms 置为原值+1000)
    updates = (base.sample(fraction=args.sample_rate, seed=42)
                   .withColumn("latency_ms", F.col("latency_ms") + 1000))
    updates_count = updates.count()
    print(f"[poc] stage=updates rows={updates_count} seconds=0", flush=True)

    # A. 现状口径: dt 分区整体重写(全分区重算 + 重写 Parquet)
    def workload_overwrite():
        (base.write.mode("overwrite")
             .partitionBy("event_date")
             .parquet("/warehouse/hfusionhub-iceberg-poc-overwrite-tmp"))

    # B. Iceberg: MERGE INTO 行级更新
    def workload_merge():
        (updates.createOrReplaceTempView("poc_updates"))
        spark.sql(f"""
            MERGE INTO hf_ice.dwd.dwd_llm_call_poc t
            USING poc_updates s
            ON t.row_id = s.row_id
            WHEN MATCHED THEN UPDATE SET t.latency_ms = s.latency_ms
        """)

    for rep in range(1, args.reps + 1):
        t0 = time.perf_counter()
        workload_overwrite()
        print(f"[poc] stage=overwrite-rep{rep} rows={init_rows} "
              f"seconds={time.perf_counter() - t0:.1f}", flush=True)

        t0 = time.perf_counter()
        updates.cache()
        updates_count = updates.count()
        workload_merge()
        print(f"[poc] stage=merge-rep{rep} rows={updates_count} "
              f"seconds={time.perf_counter() - t0:.1f}", flush=True)
        updates.unpersist()

    # ── time-travel: 合并前的旧值仍可查 ───────────────────────────────────
    # time-travel: VERSION AS OF 合并前快照 → 仍可读到"修正前"的旧值;
    # 当前版本读到"修正后"的新值(延迟 +1000)。
    sample = updates.select("row_id", F.col("latency_ms").alias("new_latency"),
                            (F.col("latency_ms") - 1000).alias("old_latency")).limit(100)
    sample.createOrReplaceTempView("poc_sample")
    old_visible = spark.sql(
        f"SELECT count(*) FROM hf_ice.dwd.dwd_llm_call_poc VERSION AS OF {init_snapshot} t "
        "JOIN poc_sample s ON t.row_id = s.row_id WHERE t.latency_ms = s.old_latency"
    ).collect()[0][0]
    now_visible = spark.sql(
        "SELECT count(*) FROM hf_ice.dwd.dwd_llm_call_poc t "
        "JOIN poc_sample s ON t.row_id = s.row_id WHERE t.latency_ms = s.new_latency"
    ).collect()[0][0]
    print(f"[poc] stage=time-travel old_visible={old_visible} "
          f"new_visible={now_visible} seconds=0", flush=True)

    # ── schema evolution ──────────────────────────────────────────────────
    spark.sql("ALTER TABLE hf_ice.dwd.dwd_llm_call_poc "
              "ADD COLUMN data_quality_flag STRING COMMENT '血缘/质量标注位'")
    cols = spark.table("hf_ice.dwd.dwd_llm_call_poc").columns
    print(f"[poc] stage=schema-evolution has_new_column={('data_quality_flag' in cols)} "
          f"columns={len(cols)}", flush=True)

    spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
