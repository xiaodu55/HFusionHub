#!/usr/bin/env python3
"""HFusionData Analytics — Spark 作业公共库。

约定:
- 存储计算解耦:Spark 直接读写 HDFS Parquet(/warehouse/hfusionhub/<layer>),
  不连接 Hive metastore;Hive 外部表(hive-sql/04-06)指向同一路径提供 SQL 层。
- 分区幂等:所有写路径按 dt 分区覆盖(mode=overwrite + dynamicPartitionOverwrite),
  任意历史 dt 可安全回补。
- ADS 结果同构回写 MySQL(V82 迁移建表),业务侧零 Hadoop 依赖消费。
"""

from __future__ import annotations

import datetime as _dt
import os

WAREHOUSE = "/warehouse/hfusionhub"


def yesterday() -> str:
    return (_dt.date.today() - _dt.timedelta(days=1)).isoformat()


def build_spark(app_name: str) -> "SparkSession":
    from pyspark.sql import SparkSession

    return (
        SparkSession.builder
        .appName(app_name)
        # on YARN 由 spark-submit --master 指定;调试可 --master 'local[*]'
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )


def ods_path(table: str) -> str:
    return f"{WAREHOUSE}/ods/{table}"


def read_ods(spark, table: str, dt: str):
    """读指定 dt 分区;分区不存在时返回空 DataFrame(列结构由首读取推断)。"""
    path = ods_path(table)
    df = spark.read.parquet(path)
    return df.where(f"dt = '{dt}'").drop("dt")


def write_partitioned(df, layer: str, table: str, dt: str) -> str:
    out = f"{WAREHOUSE}/{layer}/{table}"
    (
        df.write.mode("overwrite")
        .partitionBy("dt")
        .parquet(out)
    )
    return out


# ── MySQL ADS 回写(V82 建表;业务侧经 AnalyticsController 消费) ────────────

ADS_MYSQL_TABLES = {
    "ads_cost_daily": "ads_cost_daily",
    "ads_model_share": "ads_model_share",
    "ads_tenant_topn": "ads_tenant_topn",
    "ads_tool_success": "ads_tool_success",
    "ads_eval_quality": "ads_eval_quality",
}


def mysql_options() -> dict:
    return {
        "url": os.environ.get(
            "ANALYTICS_JDBC_URL",
            "jdbc:mysql://mysql8:3306/hfusionhub?useSSL=false&allowPublicKeyRetrieval=true"),
        "user": os.environ.get("ANALYTICS_DB_USER", "hfusion"),
        "password": os.environ.get("ANALYTICS_DB_PASSWORD", ""),
        "driver": "com.mysql.cj.jdbc.Driver",
    }


def write_mysql_mirror(df, table: str, stat_date: str = "") -> None:
    """把 ADS 结果整表覆盖回写 MySQL(与 Hive 侧 ADS 同构)。

    刻意选择"全表刷新"而非按 stat_date 增量:ADS 是聚合小表(万行级),
    全表覆盖天然幂等,且避免 JDBC sink 无法按分区删除的语义陷阱。
    """
    opts = mysql_options()
    (
        df.write.format("jdbc")
        .option("url", opts["url"])
        .option("dbtable", table)
        .option("user", opts["user"])
        .option("password", opts["password"])
        .option("driver", opts["driver"])
        .option("truncate", "true")
        .option("isolationLevel", "READ_COMMITTED")
        .mode("overwrite")
        .save()
    )
    print(f"[mysql-mirror] {table} full-refresh rows={df.count()}"
          + (f" (trigger dt={stat_date})" if stat_date else ""))
