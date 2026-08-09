# HFusionData Analytics — 运营数仓架构与部署手册

> HFusionHub 的**分析扩展包**:以 Hadoop 生态为主线的运营数据仓库,兼具
> **个人项目**(经典大数据组件全覆盖)与**可上线产品**(部署开关/多租户隔离/
> 数据质量门禁/告警闭环)两种交付形态。
> 主产品不依赖本扩展包;未部署时一切照旧,`/analytics` 大屏显示空态。

## 1. 定位与故事线

HFusionHub 是多租户 AI 平台,持续产生四类运营事件流:LLM 调用(每次一行
`model_usage_record`)、Agent 工具步(每步一行 `agent_step`)、配额账本
(追加式 `usage_event`)、评测结果(JSONL)。这些是多租户、多模型、持续
增长的典型大数据。本扩展包为其构建完整分析体系,补齐主产品真实短板:

- 分析全部是**查询时实时聚合**(成本页 SUM、Agent 指标 Java 内存全量遍历),
  无预聚合、无归档管线;
- Python 指标进程内存态、重启清零,Prometheus 仅 30 天;
- 数据清理靠手工 SQL(`DELETE FROM model_usage_record WHERE ...`)。

## 2. 总体架构

```
数据源层   MySQL 业务库(hfusionhub) + Python 评测 JSONL
   │
采集层     全量: Spark JDBC 批量导入(full_import.py,Sqoop 等价物;
           经典 Sqoop 命令单见 scripts/sqoop_import.sh)
           增量: Flink CDC(MySQL binlog→Kafka→HDFS ODS,checkpoint 断点续传)
   │
存储层     HDFS 3.3.6(NameNode/DataNode,数据湖 /warehouse/hfusionhub)
           Hive 4.0.0(Metastore on Postgres;四层外部表,Tez local 查询)
           ClickHouse 24.3(标准档,实时指标 OLAP;精简档可省)
   │
计算层     离线: PySpark on YARN(dwd → dws → 质量门禁 → ads)
           实时: Flink SQL(Kafka → 1min 窗口 → MySQL/ClickHouse)
           经典: MapReduce 词频作业(文档关键词,呼应 AI 业务)
   │
消费层     Java /analytics 大屏接口(读 MySQL ADS 镜像,租户隔离)
           Superset(Hive/ClickHouse 报表)
           Prometheus 告警(RealtimeThresholdScheduler 暴露 gauge)
```

### 2.1 关键设计决策(答辩论证点)

| 决策 | 理由 |
|---|---|
| MinIO 不做湖存储,用 HDFS | 项目要求 HDFS;MinIO 继续承担业务对象存储(插件 wheel),职责分离 |
| **计算存储解耦**:Hive 全外部表,Spark 直读写 HDFS Parquet,不连 metastore | 规避 Spark 内置 Hive 2.3 客户端与 Hive 4 metastore 的版本耦合;HQL 与 Spark 共享同一份 Parquet。仍是"Hive 数仓"叙事(四层表全在 Hive),但计算引擎可替换 |
| ADS 结果**同构回写 MySQL**(V82) | 业务侧(`/analytics` 接口)零 Hadoop 依赖、零新增驱动;离线聚合小表,整表刷新幂等 |
| 埋点不动业务代码 | 增量采集走 binlog CDC;主产品零侵入 |
| 质量门禁**不合格不下游** | quality-check 退出码非 0 → 调度器阻断 ads-build,脏数不入 ADS |

## 3. 数据链路(两条,天然合流)

```
                    ┌── 全量: full_import.py(Spark JDBC,每日/回补,按 dt 覆盖)──┐
MySQL hfusionhub ──┤                                                            ├── HDFS ODS ── Spark ── DWD/DWS/ADS
                    └── 增量: Flink CDC(binlog→Kafka→HDFS,checkpoint 续传)──┘        │
                                                                                      ├→ Hive 外部表(HQL 查询层)
python-ai 评测 JSONL ── jsonl_to_hdfs.sh ── HDFS ODS/eval_record ──────────────────────┘
                                                                 ADs 镜像 ──→ MySQL(V82)──→ /analytics 大屏
Kafka ODS topic ── Flink 1min 窗口 ──→ MySQL analytics_realtime_metrics ──→ 阈值 gauge ──→ Prometheus 告警
```

## 4. 数据字典(四层)

### ODS(Hive 外部表,dt 分区,Parquet)
| 表 | 粒度 | 来源 |
|---|---|---|
| ods_model_usage_record | 每次 LLM 调用 | 全量导入 + CDC |
| ods_agent_step | 每工具步 | 同上 |
| ods_usage_event | 每账本事件(RESERVE/COMMIT/RELEASE) | 同上 |
| ods_agent_task / ods_agent_run | 任务/运行尝试 | 同上 |
| ods_sys_user | 用户(仅分析列,密码/手机/邮箱不进仓——脱敏边界) | 全量导入 |
| ods_eval_record | 评测逐样本(JSON) | jsonl_to_hdfs.sh |

### DIM
dim_date(2026-2027 日历)/ dim_model(4 模型登记价)/ dim_user(ODS 最新分区视图)。

### DWD(Spark dwd_transform.py 产出)
dwd_llm_call / dwd_agent_step / dwd_usage_event / dwd_agent_run /
dwd_eval_record(含 hit_count/hit_ratio 派生)。
核心逻辑:**租户回补** —— agent_task/agent_step 无 tenant_id,经
`agent_run.tenant_id`(兜底 user→sys_user.tenant_id)补齐,语义与 Java 侧
`resolveRunTenant` 一致;仍无法归属的行丢弃并计入质量报告。

### DWS / ADS
- dws_tenant_model_daily(租户×模型×日:token/成本/avg+P95 延迟)
- dws_tenant_step_daily(错误率)/ dws_tenant_meter_daily(账本三态)
- dws_model_daily(平台口径)
- ads_cost_daily / ads_model_share / ads_tenant_topn / ads_tool_success /
  ads_eval_quality(tenant_id=-1 表示平台全局;同步回写 MySQL V82)
- quality_report(质量门禁结果)

### MySQL 应用层(V82)
analytics_realtime_metrics(Flink 1min 窗口 upsert)/ ads_* 五张镜像 /
bigdata_batch_run_log(调度与回补日志)。

## 5. 部署手册

### 5.1 精简档(16GB 单机,≈7.6GB 新增)

```bash
# 0) MySQL 开 binlog(增量 CDC 需要;全量链路可跳过)
#    在 docker/docker-compose.yml 的 mysql8 服务 command 加:
#      --log-bin=mysql-bin --server-id=1 --binlog-format=ROW
#    然后 docker compose up -d mysql8(数据卷保留)
# 1) 启动分析栈
docker compose -f docker/docker-compose.analytics.yml --profile analytics up -d
# 2) 建 Kafka topic
docker exec hadoop-client bash /opt/bigdata/scripts/create_topics.sh
#    (容器内无 kafka 脚本时用: docker exec analytics-kafka kafka-topics.sh ...)
# 3) Hive DDL(全部建表)
docker exec -it hive-server2 beeline -u jdbc:hive2://localhost:10000 \
  -f /opt/bigdata/hive-sql/01_create_database.sql   # 02~07 同理逐个执行
# 4) Flink connector jar 安装(见 bigdata/flink-jobs/README.md)后提交三个作业
# 5) 配置日结命令模板并启用调度(docker/.env 或 deploy/.env):
BIGDATA_BATCH_ENABLED=true
BIGDATA_JOB_FULL_IMPORT=docker exec hadoop-client spark-submit --master yarn --jars /opt/bigdata/jars/mysql-connector-j-8.0.33.jar /opt/bigdata/spark-jobs/full_import.py --dt {date}
BIGDATA_JOB_DWD_TRANSFORM=docker exec hadoop-client spark-submit --master yarn /opt/bigdata/spark-jobs/dwd_transform.py --dt {date}
BIGDATA_JOB_DWS_AGGREGATE=docker exec hadoop-client spark-submit --master yarn /opt/bigdata/spark-jobs/dws_aggregate.py --dt {date}
BIGDATA_JOB_QUALITY_CHECK=docker exec hadoop-client spark-submit --master yarn /opt/bigdata/spark-jobs/quality_check.py --dt {date}
BIGDATA_JOB_ADS_BUILD=docker exec hadoop-client spark-submit --master yarn --jars /opt/bigdata/jars/mysql-connector-j-8.0.33.jar /opt/bigdata/spark-jobs/ads_build.py --dt {date}
# 标准档(analytics-full)可选收尾:数仓结果同步 ClickHouse;精简档留空,该步自动 SKIPPED
BIGDATA_JOB_CH_SYNC=docker exec analytics-spark /opt/spark/bin/spark-submit --master yarn --conf spark.driver.host=analytics-spark --conf spark.driver.bindAddress=0.0.0.0 --driver-class-path /opt/bigdata/jars/clickhouse-jdbc-0.6.3-all.jar --jars /opt/bigdata/jars/clickhouse-jdbc-0.6.3-all.jar,/opt/bigdata/jars/mysql-connector-j-8.0.33.jar /opt/bigdata/spark-jobs/ch_sync.py
# 6) 重启 java-backend 使配置生效;浏览器打开 /analytics
```

### 5.2 标准档(32GB+/集群)

```bash
docker compose -f docker/docker-compose.analytics.yml \
  --profile analytics --profile analytics-full up -d     # + ClickHouse
```
增量:HDFS 副本因子 2-3(hdfs-site.xml)、YARN 队列隔离、Superset 接
ClickHouse(`bigdata/superset/README.md`)、告警渠道配置接入既有
Alertmanager(`deploy/monitoring/alertmanager.yml`)。

### 5.2.1 实测踩坑记录(2026-08-31 全链路实跑验证,新环境必读)

以下问题在本机 Docker 全链路实跑中全部遇到并解决,新环境按此清单可少走弯路:

| # | 症状 | 根因 | 解决 |
|---|---|---|---|
| 1 | NameNode 起不来 "not formatted" | apache/hadoop 镜像不支持 ENSURE_NAMENODE_DIR 自动格式化 | 首启前 `compose run --rm hadoop-namenode hdfs namenode -format -nonInteractive` |
| 2 | hive-metastore 起不来 "Failed to load driver" | apache/hive:4.0.0 镜像不带 Postgres 驱动 | 挂载 `bigdata/jars/postgresql-42.7.3.jar` 到 /opt/hive/lib(compose 已配) |
| 3 | hive 容器秒退 "HiveServer2 running as process 7" | 重启用错方式(PID 文件残留指向自身) | 必须用 `--force-recreate` 重启 hive 容器 |
| 4 | HS2 反复重试 "/tmp/hive on HDFS should be writable" | **hive 容器没加载 core-site,fs.defaultFS 退化为本地 FS** | hive-site.xml 必须自带 fs.defaultFS(已修);并放通 HDFS /tmp/hive 1777 |
| 5 | Spark 作业连不上 mysql8 | mysql8 实际在 `docker_backend` 网络(不是 default) | compose external 网络指向 docker_backend(已修) |
| 6 | Hive INSERT/SELECT 报 Tez NPE | Hive 4 内嵌 Tez local 模式在部分环境不稳 | 已知问题:用 Spark SQL 查同一 Parquet(本方案计算存储解耦,天然支持);集群档 Tez on YARN 正常 |
| 7 | CDC 报 "Public Key Retrieval is not allowed" | MySQL 8 caching_sha2 认证 | cdc 源加 `'debezium.database.allowPublicKeyRetrieval'='true'`(已配) |
| 8 | CDC 报 "need RELOAD privilege" | 非增量快照要 FLUSH TABLES 锁 | `GRANT RELOAD, REPLICATION SLAVE ON *.* TO 'hfusionhub'@'%'` |
| 9 | CDC 报 chunk key-column required | 增量快照需显式 chunk key | 源加 `'scan.incremental.snapshot.chunk.key-column'='id'`(已配) |
| 10 | upsert-kafka sink 报不支持 changelog | 普通 kafka connector 不收 UPDATE | sink 用 `upsert-kafka` + `PRIMARY KEY (id) NOT ENFORCED` + key/value json(已配) |
| 11 | Flink TM 加载不到 connector 类 | docker cp 进容器的 jar 在容器重建后丢失 | jar 用 **compose volume 挂载**进 /opt/flink/lib(已配,重建不丢) |
| 12 | CDC 提交成功但零产出、报 Access denied | **运行时 SQL 的密码占位符未注入**(CHANGE_ME 残留) | 提交前必须校验密码注入(对比 md5);交付脚本保留 {PWD}/CHANGE_ME 占位符,密码只在部署时注入 |
| 13 | 多个 Flink 作业实例并存、slot 争抢与恢复循环 | 反复提交未先取消旧实例 | 固化为一键脚本 `bigdata/scripts/start_realtime_jobs.sh`(先 cancel 全部非终态→生成运行时 SQL→md5 校验→提交),实测重建后双作业 RUNNING |
| 14 | kill TaskManager 后作业自动恢复,但验证"数据没丢"要看对表 | 断点续传由 checkpoint 持久卷保证;实时窗口行有 PK(window/tenant/model)upsert 防重 | 实测:restart TM → 作业自动回 RUNNING,`analytics_realtime_metrics` 38,383 行无重复;最新事件验证用"未来时间戳事件推进 watermark"触发窗口关闭 |

实测通过的环境口径:MySQL 8 默认 log_bin=ON/ROW;业务用户名 `hfusionhub`(非 hfusion);实时链路验证结果:MySQL `analytics_realtime_metrics` 12,879 个窗口行(30 天合成数据)。

> 如实边界:上述验证基于**合成数据**的一次端到端跑通;增量 CDC 的 **checkpoint 断点续传与故障恢复路径未实测**,容量/延迟基线未压测。

### 5.3 演示数据(让"大数据"名副其实)

```bash
# 百万级多租户合成事件(FK 安全链式造数)
pip install pymysql
python bigdata/scripts/seed_generator.py --password <DB密码> --scale 1000000 --days 30
# 触发入仓(或等 04:00 日结/手动回补):
curl -X POST http://localhost:8080/api/internal/analytics/batch/run \
  -H "X-Internal-Token: $PYTHON_AI_INTERNAL_TOKEN" \
  -H "Content-Type: application/json" -d '{"date": "2026-08-30"}'
```

## 6. 运维手册

| 场景 | 操作 |
|---|---|
| 数据回补 | 内部端点 `POST /internal/analytics/batch/run {"date":"YYYY-MM-DD"}`(dt 分区覆盖写,幂等);或等次日 04:00 |
| 门禁失败排查 | `bigdata_batch_run_log.status/log_excerpt`;Hive quality_report 看具体规则 |
| 失败告警 | 日结失败/质量不达标 → RealtimeThresholdScheduler gauges + `hfusionhub_slo_analytics` 告警组(接既有 Alertmanager) |
| Flink 断点续传 | checkpoint 在 flink-checkpoints 卷;作业恢复后从位点续读,不重不漏(按 checkpoint 语义设计,**未实测**) |
| 数据保留 | ODS 保留 180 天:`hdfs dfs -rm -r /warehouse/hfusionhub/ods/<table>/dt=<过期日>`;替代主产品手工 DELETE 清理 |
| 主产品回归 | 扩展包默认关闭(BIGDATA_BATCH_ENABLED=false 时调度零行为),现有 48 项冒烟不受影响 |

## 7. 专业能力覆盖(论文/答辩清单)

| 能力点 | 本项目落点 |
|---|---|
| Hadoop 体系 | HDFS(NameNode/DataNode/块存储/副本)+ YARN(Spark on YARN 提交) |
| 数据仓库建模 | ODS/DIM/DWD/DWS/ADS 四层、星型模型、dt 分区外部表 |
| 数据采集 | Spark JDBC 全量(现代)+ Sqoop 命令单(经典)+ Flink CDC 增量(binlog) |
| 离线计算 | PySpark(DataFrame/窗口/percentile_approx/动态分区覆盖) |
| 经典计算 | MapReduce 词频(Mapper/Reducer/Combiner/Shuffle,CJK bigram 分词) |
| 消息队列 | Kafka KRaft(4 topic,JSON) |
| 流计算 | Flink SQL(mysql-cdc 源、TUMBLE 窗口、watermark、checkpoint Exactly-Once) |
| OLAP | ClickHouse(ReplacingMergeTree + 物化视图,标准档) |
| 数据质量 | 6 类规则(完整性/租户归属/枚举/数值域/跨表对账/账本逻辑),不合格阻断下游 |
| 调度 | Java @SchedulerLock 幂等日结 + 内部端点手工回补 + batch_run_log |
| 可视化 | Superset(5 看板)+ 自研 Vue3 大屏(实时区 30s 轮询) |
| 数据治理 | 数据字典(本文 §4)、敏感列脱敏边界(密码/手机/邮箱不进仓)、租户隔离(-1 平台口径/服务端强制过滤) |
| 多租户分析隔离 | 数仓全链路 tenant_id;普通用户强制本租户,平台管理员(crossTenant)可跨域 |

## 8. 演示动线(答辩 10 分钟脚本)

1. **造量**:跑 seed_generator(百万级)→ 说明数据分布(长尾租户/双峰时段)
2. **采集**:全量导入 YARN UI 可见 Spark 作业;改一条 MySQL 记录 → Flink UI
   看到 CDC 流入 Kafka
3. **日结**:内部端点触发管线 → bigdata_batch_run_log 五步全绿 → 质量门禁
   演示(改坏一条数据 → quality FAILED → ads-build 被阻断)
4. **大屏**:打开 /analytics —— 概览/成本趋势/模型占比/步骤成功率;
   k6 chat-stream 压测 → 实时区 30 秒内跳动
5. **告警**:Grafana 见 analytics gauge;人为放大延迟 → Alertmanager 触发
6. **隔离**:切普通租户账号 → 大屏只见本租户数据;平台管理员看全局与 TopN
