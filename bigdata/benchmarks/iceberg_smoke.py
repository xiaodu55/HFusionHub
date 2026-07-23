from pyspark.sql import SparkSession

spark = (SparkSession.builder.appName("iceberg-smoke")
         .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
         .config("spark.sql.catalog.hf_ice", "org.apache.iceberg.spark.SparkCatalog")
         .config("spark.sql.catalog.hf_ice.type", "hadoop")
         .config("spark.sql.catalog.hf_ice.warehouse", "hdfs:///warehouse/hfusionhub-iceberg")
         .getOrCreate())
spark.sparkContext.setLogLevel("WARN")
spark.sql("DROP TABLE IF EXISTS hf_ice.smoke.t1")
spark.sql("CREATE NAMESPACE IF NOT EXISTS hf_ice.smoke")
spark.sql("CREATE TABLE hf_ice.smoke.t1 (id INT, v STRING) USING ICEBERG")
spark.sql("INSERT INTO hf_ice.smoke.t1 VALUES (1, 'a'), (2, 'b')")
n = spark.sql("SELECT count(*) FROM hf_ice.smoke.t1").collect()[0][0]
spark.sql("DELETE FROM hf_ice.smoke.t1 WHERE id = 1")
n2 = spark.sql("SELECT count(*) FROM hf_ice.smoke.t1").collect()[0][0]
hist = spark.sql("SELECT committed_at, snapshot_id FROM hf_ice.smoke.t1.snapshots ORDER BY committed_at").collect()
print(f"[smoke] rows_after_insert={n} rows_after_delete={n2} snapshots={len(hist)}")
spark.stop()
