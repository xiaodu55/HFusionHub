# ADR-002: 向量库选型——Milvus（Standalone 生产 + milvus-lite 开发双模式）

- 状态：已采纳（2026-09-08 补写）
- 关联：`python-ai/app/core/vectorstore/factory.py`（模式选择与生产守卫）、
  `milvus_lite.py` / `milvus_cluster.py`（双实现）、
  `docker/docker-compose.yml`（milvus v2.6.6 + 外部 etcd + attu）、
  [ADR-003](ADR-003-hmac-callback-idempotent-indexing.md)（重索引幂等性）

## 背景

RAG 需要一个可私有部署、可平滑扩容、支持租户隔离命名空间的向量库；
同时开发/单测环境不应强制拉起整套向量库基础设施。候选：
pgvector（需 PostgreSQL，而本项目 OLTP 是 MySQL，引入第二存储引擎
得不偿失）、Elasticsearch（重、JVM 资源占用大、超出向量检索需求）、
FAISS 内存索引（无持久化与多实例语义）。

## 决策

1. **选 Milvus**：向量维度 1024（bge-m3，COSINE）；生产/预发强制
   `VECTOR_STORE_MODE=cluster`（Milvus Standalone v2.6.6 + 外部 etcd，
   Attu 控制台可选）——`factory.py` 在 `SERVER_ENV ∈ {production,
   staging}` 下检测到 lite 模式直接 `SystemExit(1)` fail-fast；
2. **开发模式 milvus-lite**：本地文件 co-store（JSON 分块存储），
   零基础设施；带 `(mtime_ns, size)` 缓存与租户隔离 key（R15-2/2.8）；
3. **租户隔离靠 collection 命名空间**（per-tenant collection），
   检索侧再叠加 ACL metadata 过滤（见第 35/36 批 visibility 收口）；
4. **写路径幂等**：chunk_id 确定性生成 + `insert_chunks` 走
   `client.upsert` 按主键替换（第三十六批修复重索引重复插入）；
   大规模读取用 `queryIterator` 分页，规避单次查询行数上限（R15-18）。

## 结果与测量

- 开发机零额外容器即可跑通全链路（lite 模式），CI 的 Python 全量测试
  不依赖 Milvus 服务；生产拓扑经 docker-compose 与 Helm 双通道校验
  （helm lint + kubeconform 门禁）；
- k6/基线实测：10K 量级 chunk 向量检索 50–200ms，瓶颈不在向量库而在
  embedding 生成（见 `docs/baselines/`，R16-P1 优化对象）。

## 后果与边界

- 生产拓扑引入 milvus + etcd 两个额外容器（资源 limits 已对齐 Helm）；
- lite/cluster 双实现存在行为对齐成本——凡涉及写入语义的修改必须
  双侧同步（第三十六批 upsert 修复即一例），这是双模式换取开发体验
  的持续税；
- collection per-tenant 在租户量级极大时需评估 collection 数上限，
  当前个人私有部署量级不构成约束。
