#!/usr/bin/env python3
"""HFusionData Analytics — 数据质量检查。

规则集(全部落在 Hive quality_report 表,passed=false 任一条 → 退出码 1,
调度器据此阻断 ADS 回写并告警):

  R1 完整性    ODS 关键表 dt 分区存在且行数 > 0
  R2 租户归属  dwd_llm_call / dwd_agent_step 的 tenant_id 空值率 = 0
  R3 枚举域    request_type ∈ {chat,embedding,agent,evaluation};
               operation ∈ {RESERVE,COMMIT,RELEASE};meter 域合法
  R4 数值域    tokens/amount/latency 非负;cost_usd 非负
  R5 跨表对账  dwd_llm_call 行数 == dwd 明细口径聚合(防丢数)
  R6 逻辑一致  usage_event 同 request_id 的 COMMIT 量 <= RESERVE 量

用法: spark-submit --master yarn quality_check.py --dt 2026-08-30
"""

import argparse
import json
import os
import sys

import pyspark.sql.functions as F

from _common import build_spark, WAREHOUSE, write_partitioned

# 规则配置(枚举域/开关/阈值)外置为本文件同目录的 quality_rules.json:
# 枚举域必须与 Java 侧 UsageRequestType/UsageOperation/UsageMeter 枚举一致,
# 新增计量项由"改代码发版"降级为"改配置"。缺文件/缺键时回退内置默认。
_DEFAULT_CONFIG = {
    "enums": {
        "request_type": ["chat", "embedding", "agent", "evaluation"],
        "operation": ["RESERVE", "COMMIT", "RELEASE"],
        "meter": ["chat_tokens", "agent_tokens", "index_chunks", "plugin_executions",
                  "bid_projects", "tender_elements", "bid_draft_chars", "bid_check_reports"],
    },
    "enabled": {
        "r1_ods_partition_nonempty": True,
        "r2_tenant_null_rate": True,
        "r3_enum_domains": True,
        "r4_negative_values": True,
        "r5_ods_dwd_row_drift": True,
        "r6_ledger_commit_over_reserve": True,
    },
    "thresholds": {"ods_dwd_row_drift_ratio": 0.01},
}


def load_rules_config() -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    merged = json.loads(json.dumps(_DEFAULT_CONFIG))
    for path in (os.path.join(here, "quality_rules.json"),
                 "/opt/bigdata/spark-jobs/quality_rules.json"):
        try:
            with open(path, encoding="utf-8") as f:
                overlay = json.load(f)
            for section, values in overlay.items():
                if isinstance(values, dict):
                    merged.setdefault(section, {}).update(values)
                else:
                    merged[section] = values
        except (OSError, ValueError):
            continue
    return merged


def read_ods(spark, table, dt):
    return spark.read.parquet(f"{WAREHOUSE}/ods/{table}").where(f"dt = '{dt}'").drop("dt")


def read_dwd(spark, table, dt):
    return spark.read.parquet(f"{WAREHOUSE}/dwd/{table}").where(f"dt = '{dt}'").drop("dt")


def main():
    parser = argparse.ArgumentParser(description="Data quality gate")
    parser.add_argument("--dt", required=True)
    args = parser.parse_args()
    dt = args.dt

    spark = build_spark("HFusionData-Quality")
    spark.sparkContext.setLogLevel("WARN")

    config = load_rules_config()
    enabled = config["enabled"]
    enums = config["enums"]

    results = []  # (table, rule, value, threshold, passed, detail)

    def record(table, rule, value, threshold, passed, detail=""):
        results.append((dt, table, rule, float(value), float(threshold), bool(passed), detail))

    # ── R1 完整性 ───────────────────────────────────────────────────────────
    if enabled["r1_ods_partition_nonempty"]:
        for table in ("model_usage_record", "agent_step", "usage_event", "agent_task"):
            try:
                cnt = read_ods(spark, table, dt).count()
                record(table, "ods_partition_nonempty", cnt, 0, cnt > 0,
                       f"ODS {table} dt={dt} 行数={cnt}")
            except Exception as exc:  # noqa: BLE001 — 分区不存在也记为不通过
                record(table, "ods_partition_nonempty", 0, 0, False, f"读取失败: {exc}")

    # ── R2 租户归属 ─────────────────────────────────────────────────────────
    if enabled["r2_tenant_null_rate"]:
        for table in ("dwd_llm_call", "dwd_agent_step", "dwd_agent_run"):
            df = read_dwd(spark, table, dt)
            total = df.count()
            nulls = df.where(F.col("tenant_id").isNull()).count()
            null_rate = nulls / total if total else 0.0
            record(table, "tenant_null_rate", null_rate, 0.0, null_rate == 0.0,
                   f"空租户 {nulls}/{total}")

    # ── R3 枚举域(域清单来自 quality_rules.json) ────────────────────────────
    calls = read_dwd(spark, "dwd_llm_call", dt)
    usage = read_dwd(spark, "dwd_usage_event", dt)
    if enabled["r3_enum_domains"]:
        bad_type = calls.where(
            ~F.col("request_type").isin(enums["request_type"])).count()
        record("dwd_llm_call", "request_type_enum_violation", bad_type, 0, bad_type == 0)

        bad_op = usage.where(~F.col("operation").isin(enums["operation"])).count()
        record("dwd_usage_event", "operation_enum_violation", bad_op, 0, bad_op == 0)
        bad_meter = usage.where(~F.col("meter").isin(enums["meter"])).count()
        record("dwd_usage_event", "meter_enum_violation", bad_meter, 0, bad_meter == 0)

    # ── R4 数值域 ───────────────────────────────────────────────────────────
    if enabled["r4_negative_values"]:
        neg = calls.where((F.col("total_tokens") < 0) | (F.col("cost_usd") < 0)
                          | (F.col("latency_ms") < 0)).count()
        record("dwd_llm_call", "negative_values", neg, 0, neg == 0)
        neg_usage = usage.where(F.col("amount") < 0).count()
        record("dwd_usage_event", "negative_amount", neg_usage, 0, neg_usage == 0)

    # ── R5 跨表对账(ODS 与 DWD 行数一致,允许租户回补丢弃少量不可归属行) ────
    if enabled["r5_ods_dwd_row_drift"]:
        ods_calls = read_ods(spark, "model_usage_record", dt).count()
        dwd_calls = calls.count()
        drift = ods_calls - dwd_calls
        drift_ratio = drift / ods_calls if ods_calls else 0.0
        drift_threshold = config["thresholds"]["ods_dwd_row_drift_ratio"]
        record("dwd_llm_call", "ods_dwd_row_drift_ratio", drift_ratio, drift_threshold,
               drift_ratio <= drift_threshold, f"ODS {ods_calls} -> DWD {dwd_calls}")

    # ── R6 账本逻辑(COMMIT <= RESERVE,同 request_id+meter) ────────────────
    if enabled["r6_ledger_commit_over_reserve"]:
        ledger = (
            usage.groupBy("request_id", "meter")
            .agg(
                F.sum(F.when(F.col("operation") == "RESERVE", F.col("amount")).otherwise(0))
                .alias("reserved"),
                F.sum(F.when(F.col("operation") == "COMMIT", F.col("amount")).otherwise(0))
                .alias("committed"),
            )
        )
        over_commit = ledger.where(F.col("committed") > F.col("reserved")).count()
        record("dwd_usage_event", "commit_over_reserve", over_commit, 0, over_commit == 0)

    # ── 落库 quality_report ─────────────────────────────────────────────────
    # 注意: 不能用 spark.createDataFrame(本地列表) —— 那会在执行器上拉起
    # Python worker,要求所有 NodeManager 装有 python3(本栈 NM 为 CentOS 7,
    # 无 python3)。这里改用驱动端 VALUES SQL 构造 DataFrame,执行器零 Python 依赖。
    def esc(text: str) -> str:
        return str(text).replace("\\", "\\\\").replace("'", "\\'")

    tuples = ", ".join(
        "('{}', '{}', '{}', {}, {}, {}, '{}')".format(
            esc(r[0]), esc(r[1]), esc(r[2]), float(r[3]), float(r[4]),
            "true" if r[5] else "false", esc(r[6] if len(r) > 6 else ""))
        for r in results
    )
    report = spark.sql(
        "SELECT stat_date, table_name, rule_name, metric_value, threshold, "
        "passed, detail FROM VALUES "
        f"{tuples} AS t(stat_date, table_name, rule_name, "
        "metric_value, threshold, passed, detail)"
    )
    write_partitioned(report, "quality", "quality_report", dt)
    report.orderBy("passed", "table_name").show(truncate=False)

    failed = [r for r in results if not r[5]]
    print(f"[quality] dt={dt} 规则 {len(results)} 条,不通过 {len(failed)} 条")
    spark.stop()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
