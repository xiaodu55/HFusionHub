#!/usr/bin/env python3
"""HFusionData Analytics — DWD 明细事实层构建。

输入: ODS(dt 分区 Parquet)
输出: dwd_llm_call / dwd_agent_step / dwd_usage_event / dwd_agent_run /
      dwd_eval_record(dt 分区 Parquet)

核心逻辑:
1. 租户回补 —— 与 Java 侧 resolveRunTenant 语义一致:
   - model_usage_record.tenant_id 为空 → 经 agent_task_id 关联 agent_run.tenant_id
   - agent_task/agent_step 无 tenant_id → 经 agent_run.run_id/task_id 回补
   - agent_task 兜底走 user 维表(sys_user.tenant_id)
2. event_date 取事件真实 created_at 日期(回补口径,可能与导入 dt 不同)
3. eval_record:解析期望/检索文档 ID 集合,派生 hit_count/hit_ratio

用法:
  spark-submit --master yarn dwd_transform.py --dt 2026-08-30
"""

import argparse

from pyspark.sql import DataFrame, functions as F

from _common import build_spark, read_ods, write_partitioned


def parse_args():
    parser = argparse.ArgumentParser(description="ODS -> DWD transform")
    parser.add_argument("--dt", required=True, help="数据日期 YYYY-MM-DD")
    return parser.parse_args()


def _backfill_tenant_for_calls(spark, dt: str) -> DataFrame:
    mur = read_ods(spark, "model_usage_record", dt)
    run_map = (
        read_ods(spark, "agent_run", dt)
        .select(F.col("id").alias("run_id"), F.col("tenant_id").alias("run_tenant"))
    )
    task_map = (
        read_ods(spark, "agent_task", dt)
        .select(F.col("id").alias("task_id"), F.col("user_id").alias("task_user"))
    )
    user_map = (
        read_ods(spark, "sys_user", dt)
        .select(F.col("id").alias("user_key"), F.col("tenant_id").alias("user_tenant"))
    )
    task_tenant = (
        task_map.join(user_map, task_map.task_user == user_map.user_key, "left")
        .select("task_id", "user_tenant")
    )

    return (
        mur
        .join(run_map, mur.agent_task_id == run_map.run_id, "left")
        .join(task_tenant, mur.agent_task_id == task_tenant.task_id, "left")
        .withColumn(
            "tenant_resolved",
            F.coalesce(
                F.col("tenant_id"),          # 原生列(聊天路径)
                F.col("run_tenant"),          # Agent 路径: run.tenant_id
                F.col("user_tenant"),         # 兜底: user -> tenant
            ),
        )
        .where(F.col("tenant_resolved").isNotNull())   # 仍无法归属的行进质量报告
    )


def build_dwd(spark, dt: str) -> dict:
    stats = {}

    # ── dwd_llm_call ────────────────────────────────────────────────────────
    calls = _backfill_tenant_for_calls(spark, dt).select(
        F.col("tenant_resolved").alias("tenant_id"),
        "user_id", "conversation_id", "agent_task_id",
        "model", "provider", "request_type",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "cost_usd", "latency_ms", "created_at",
        F.date_format("created_at", "yyyy-MM-dd").alias("event_date"),
    )
    stats["dwd_llm_call"] = write_partitioned(calls, "dwd", "dwd_llm_call", dt)

    # ── dwd_agent_step / dwd_agent_run(经 run 原生 tenant_id) ───────────────
    runs = (
        read_ods(spark, "agent_run", dt)
        .where(F.col("tenant_id").isNotNull())
        .select(
            "tenant_id", "task_id", "run_uuid", "attempt_number", "status",
            "model", "tool_calls_count", "error_code", "failed_tool",
            "duration_ms", "created_at",
            F.date_format("created_at", "yyyy-MM-dd").alias("event_date"),
        )
    )
    stats["dwd_agent_run"] = write_partitioned(runs, "dwd", "dwd_agent_run", dt)

    # agent_step 无租户列,经 ods_agent_step.run_id -> ods_agent_run.id 回补
    step_run = (
        read_ods(spark, "agent_step", dt)
        .join(
            read_ods(spark, "agent_run", dt)
            .select(F.col("id").alias("run_id"), F.col("tenant_id").alias("run_tenant")),
            "run_id", "left")
        .where(F.col("run_tenant").isNotNull())
        .select(
            F.col("run_tenant").alias("tenant_id"),
            "run_id", "sequence", "step_type", "action", "duration_ms",
            "error_code",
            F.col("error_code").isNotNull().alias("is_error"),
            "created_at",
            F.date_format("created_at", "yyyy-MM-dd").alias("event_date"),
        )
    )
    stats["dwd_agent_step"] = write_partitioned(step_run, "dwd", "dwd_agent_step", dt)

    # ── dwd_usage_event ─────────────────────────────────────────────────────
    usage = read_ods(spark, "usage_event", dt).where(F.col("tenant_id").isNotNull()).select(
        "tenant_id", "meter", "operation", "request_id", "window_key",
        "amount", "ref_type", "ref_id", "created_at",
        F.date_format("created_at", "yyyy-MM-dd").alias("event_date"),
    )
    stats["dwd_usage_event"] = write_partitioned(usage, "dwd", "dwd_usage_event", dt)

    # ── dwd_eval_record(JSON → 结构化,派生命中指标) ───────────────────────
    # 评测 JSONL 未入湖时该 ODS 分区不存在 —— 跳过而非报错(评测链路可选)
    sc = spark.sparkContext
    hpath = sc._jvm.org.apache.hadoop.fs.Path(_ods_eval_path(dt))
    if not hpath.getFileSystem(sc._jsc.hadoopConfiguration()).exists(hpath):
        print(f"[skip] ods_eval_record dt={dt} 不存在(评测 JSONL 未入湖),跳过 eval 明细")
        return stats

    def _ids(col):
        return F.split(F.regexp_replace(F.coalesce(F.col(col), F.lit("")), r"[\[\]\"' ]", ""), ",")

    eval_df = spark.read.json(f"{_ods_eval_path(dt)}")
    eval_out = (
        eval_df
        .withColumn("expected_document_ids", _ids("expected_document_ids"))
        .withColumn("retrieved_document_ids", _ids("retrieved_document_ids"))
        .withColumn(
            "hit_count",
            F.size(F.array_intersect("expected_document_ids", "retrieved_document_ids")))
        .withColumn("expected_count", F.size("expected_document_ids"))
        .withColumn(
            "hit_ratio",
            F.when(F.col("expected_count") > 0,
                   F.col("hit_count") / F.col("expected_count")).otherwise(F.lit(None)))
        .select(
            "query_id", "query", "final_status", "ttft_ms", "latency_ms",
            "requires_rag", "expected_document_ids", "retrieved_document_ids",
            "hit_count", "expected_count", "hit_ratio",
            F.date_format(F.to_timestamp("recorded_at"), "yyyy-MM-dd").alias("event_date"),
        )
    )
    stats["dwd_eval_record"] = write_partitioned(eval_out, "dwd", "dwd_eval_record", dt)

    return stats


def _ods_eval_path(dt: str) -> str:
    return f"/warehouse/hfusionhub/ods/eval_record/dt={dt}"


def main():
    args = parse_args()
    spark = build_spark("HFusionData-DWD")
    spark.sparkContext.setLogLevel("WARN")
    stats = build_dwd(spark, args.dt)
    for name, path in stats.items():
        print(f"[ok] {name} -> {path} (dt={args.dt})")
    spark.stop()


if __name__ == "__main__":
    main()
