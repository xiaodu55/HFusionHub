from pyspark.sql import SparkSession
spark = SparkSession.builder.appName("inspect").getOrCreate()
df = spark.read.parquet("hdfs://hadoop-namenode:9000/warehouse/hfusionhub/ads/ads_cost_daily")
df.printSchema()
print("count:", df.count())
