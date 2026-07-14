from pyspark.sql import SparkSession
spark = SparkSession.builder.appName("verify").getOrCreate()
spark.sql("CREATE DATABASE IF NOT EXISTS hfusionhub LOCATION '/warehouse/hfusionhub'")
for name, path in [("dws_tenant_model_daily", "dws/dws_tenant_model_daily"),
                   ("ads_cost_daily", "ads/ads_cost_daily")]:
    spark.sql(f"""
      CREATE OR REPLACE TEMP VIEW {name} USING parquet
      OPTIONS (path 'hdfs://hadoop-namenode:9000/warehouse/hfusionhub/{path}')""")
print("=== 近 7 天模型成本(与 Hive 同口径,Spark SQL 执行) ===")
spark.sql("""SELECT model, SUM(call_count) AS calls, ROUND(SUM(cost_usd),2) AS cost
             FROM dws_tenant_model_daily WHERE stat_date >= '2026-08-25'
             GROUP BY model ORDER BY cost DESC""").show()
print("=== ADS 平台口径最近 3 天 ===")
spark.sql("""SELECT stat_date, SUM(call_count) AS calls, ROUND(SUM(cost_usd),2) AS cost
             FROM ads_cost_daily WHERE tenant_id = -1
             GROUP BY stat_date ORDER BY stat_date DESC LIMIT 3""").show()
