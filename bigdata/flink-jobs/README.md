# HFusionData Analytics — Flink 作业

CDC 增量采集与实时聚合的 Flink SQL 作业集。提交前需按下面步骤安装 connector jar。

## 1. Connector 安装(一次性)

**主方式(实测)**:docker-compose.analytics.yml 已把这 4 个 jar 以 volume
挂载进两个 Flink 容器的 `/opt/flink/lib/`(见 x 服务 volumes 段)——
容器重建不丢,拉齐 jar 后无需手动操作:

```yaml
    volumes:
      - ../bigdata/jars/flink-sql-connector-kafka-3.1.0-1.18.jar:/opt/flink/lib/...:ro
      - ../bigdata/jars/flink-connector-jdbc-3.1.2-1.18.jar:/opt/flink/lib/...:ro
      - ../bigdata/jars/flink-sql-connector-mysql-cdc-3.0.1.jar:/opt/flink/lib/...:ro
      - ../bigdata/jars/mysql-connector-j-8.0.33.jar:/opt/flink/lib/...:ro
```

> ⚠️ 备用方式(docker cp)在容器重建后会丢失——**不要**只用 docker cp。
> 注意:flink-sql-connector-mysql-cdc 的 Maven group 是 `com.ververica`
> (不是 org.apache.flink),从 aliyun 镜像拉取:`com/ververica/...`。
> 该 jar 不含 Catalog 工厂——请用逐表 mysql-cdc source 方案(见 cdc_ingest.sql,
> 并配 `scan.incremental.snapshot.chunk.key-column` + `debezium.database.
> allowPublicKeyRetrieval=true`),版本与 Flink 1.18 匹配:

| jar | 用途 | 获取方式 |
|---|---|---|
| `flink-sql-connector-mysql-cdc-3.0.1.jar` | MySQL binlog CDC | Maven Central: com.ververica |
| `flink-connector-jdbc-3.1.2-1.18.jar` | MySQL/ClickHouse JDBC sink | Maven Central |
| `mysql-connector-j-8.0.33.jar` | JDBC 驱动 | Maven Central |
| `flink-sql-connector-kafka-3.1.0-1.18.jar` | Kafka source/sink | Maven Central |
| `flink-parquet-1.18.1.jar` | ODS Parquet 落地 | Flink 发行版 `opt/` 目录 |

```bash
# 示例(宿主机执行;下载到 bigdata/flink-jobs/jars/ 再拷入容器)
docker cp bigdata/flink-jobs/jars/. flink-jobmanager:/opt/flink/lib/
docker cp bigdata/flink-jobs/jars/. flink-taskmanager:/opt/flink/lib/
docker restart flink-jobmanager flink-taskmanager
```

## 2. Source/Sink catalog DDL

> **实测修正(2026-08-31 全链路实跑)**:`-i` 预载整文件在 sql-client 有解析边界问题,
> 实际提交采用**合并单文件**方式——把 00_catalogs.sql 的 sink/source 定义与作业 INSERT
> 拼成一个 `_run_cdc.sql` / `_run_realtime.sql` 后 `-f` 提交(仓库内此两文件由部署时
> 从模板生成,密码占位符 CHANGE_ME 必须在生成时注入并在提交前 md5 校验)。
> sink 端实测采用 **upsert-kafka**(PK=id):CDC 源产生 changelog,普通 kafka
> connector 不收 UPDATE;下游实时读以 plain kafka source 消费 value 流即可。

`00_catalogs.sql` 定义所有 Kafka topic source(JSON)、HDFS filesystem sink
(Parquet,dt 分区)、MySQL JDBC sink(`analytics_realtime_metrics`,V82 迁移建表)、
ClickHouse sink(标准档)。提交作业时用 `sql-client.sh` 的 `-i` 预载:

```bash
docker exec -it flink-jobmanager bash
/opt/flink/bin/sql-client.sh -i /opt/flink/usrlib/analytics/00_catalogs.sql \
  -f /opt/flink/usrlib/analytics/cdc_ingest.sql
/opt/flink/bin/sql-client.sh -i /opt/flink/usrlib/analytics/00_catalogs.sql \
  -f /opt/flink/usrlib/analytics/ods_filesink.sql
/opt/flink/bin/sql-client.sh -i /opt/flink/usrlib/analytics/00_catalogs.sql \
  -f /opt/flink/usrlib/analytics/realtime_metrics.sql
```

> `cdc_ingest.sql` 中 MySQL 密码占位 `CHANGE_ME` 必须替换(建议用
> `-Dpipeline` 变量或环境注入,不要把真实密码写进版本库)。

## 3. 提交顺序与断点续传

1. `bash /opt/bigdata/scripts/create_topics.sh`(建 topic)
2. `cdc_ingest.sql`(initial 快照 + binlog 增量 → Kafka)
3. `ods_filesink.sql`(Kafka → HDFS ODS)
4. `realtime_metrics.sql`(Kafka → 1min 窗口 → MySQL/ClickHouse)

Checkpoint 30s 一次,落在 `flink-checkpoints` 卷;作业失败后
`flink run -s <checkpoint-path>` 或 SQL client `SET execution.savepoint`
恢复 —— **不重不漏**。Kafka source 从 group offsets 续读,
MySQL CDC 从 binlog 位点续读。

## 4. 与告警体系的汇合

`realtime_metrics.sql` 写入的 `analytics_realtime_metrics`(MySQL)由
Java 侧 `RealtimeThresholdScheduler` 每 60s 采样,经 Micrometer 暴露
`analytics_error_rate` / `analytics_p95_latency_ms` / `analytics_cost_rate`
三个 gauge,`deploy/monitoring/alert_rules.yml` 新增对应告警规则 ——
复用主产品既有 Prometheus/Alertmanager 链路,不引入新告警组件。
