# HFusionHub 生产运维手册

> 面向生产值班 / SRE / 平台管理员。本文档合并原 PRODUCTION_OPS.md（运维操作）、
> PRODUCTION_CHECKLIST.md（上线前检查清单）与 DR_VECTORS.md（向量库容灾）为
> 唯一运维手册。覆盖：上线前检查清单、Runner TLS 证书生成与轮换、插件镜像 digest
> 发布与登记、配额账本排查、Agent 执行失败 / 租户拒绝 / Runner 不可达定位、
> 向量库容灾备份与恢复。所有命令均可在 Linux 或 Docker Desktop（Windows）环境中执行。

## 0. 上线前检查清单

> 原 `docs/PRODUCTION_CHECKLIST.md` 内容。**生产环境密码等敏感值一律从
> `docker/.env` / `deploy/.env` 读取，不要硬编码到文档或代码中。**

### 🔐 安全配置（必需项，上线前必须完成）

- [ ] **修改所有默认密码** — 运行 `bash scripts/rotate-secrets.sh` 生成全部密钥并按指引同步两侧 `.env`（第十五轮 R15-26 落地脚本；`--check` 可扫描弱默认值与缺失的 `MODEL_CREDENTIAL_ENCRYPTION_KEY`）；MySQL 密码的库内落实用 `bash scripts/rotate-db-password.sh --apply --yes`（经 stdin ALTER，root/hfusionhub 账户），重启栈后 `--check` 复核
- [ ] **配置真实 DeepSeek API Key** — `python-ai/.env` → `DEEPSEEK_API_KEY`（当前已配置真实 key，聊天默认 DeepSeek 优先，Ollama 降级为 embedding/离线）
- [ ] **更新内部通信令牌** — `docker/.env` → `PYTHON_AI_INTERNAL_TOKEN`、`PLUGIN_RUNNER_SECRET_KEY`（32 字符随机字符串，两端一致）
- [ ] **启用 HTTPS** — 参考落地样例 `deploy/nginx-https.conf.example`（第十五轮 R15-26：Let's Encrypt certbot 全流程 + SSE 透传 + HSTS + 管理端口/runner 端口不对外清单）
- [ ] **CORS 白名单** — `app.cors.allow-any-origin=false`（第十五轮起代码默认值即为 false）并配置 `app.cors.allowed-origins=https://your-domain.com`；开发/内网穿透需显式开启 any-origin（启动日志会大声告警）
- [ ] **Sa-Token JWT 密钥** — `docker/.env` → `SA_TOKEN_JWT_SECRET_KEY`（建议 64 字符）
- [ ] **关闭或限制 Swagger UI** — 生产 `springdoc.swagger-ui.enabled=false` 或 IP 白名单（详见 [SWAGGER_UI.md](SWAGGER_UI.md)）

### 🗄️ 数据库与持久化

- [ ] **Flyway 迁移验证** — 确保 V1–V78 全部成功应用；检查 `flyway_schema_history` 表状态
- [ ] **备份策略** — 脚本已就绪：`scripts/backup-data.ps1`（MySQL mysqldump）+ `scripts/backup_milvus.sh`（Milvus 卷快照）；cron 示例 `0 3 * * * cd /opt/hfusionhub && ./scripts/backup_milvus.sh /backups/milvus`；恢复演练见下文「备份恢复演练」
- [ ] **Redis 持久化** — AOF 已启用（`appendonly yes`）；RDB 每小时备份（`save 3600 1`）
- [ ] **卷可写性** — 应用容器以钉死的 uid 10001 运行、helm 侧同号 fsGroup（见「10. 卷属主与运行身份」）；升级到钉死 uid 前建过的卷需一次性 chown。已实测：python 镜像在真实 docker 上三个挂载点均可写（§10.2 M1）；未实测：java 镜像（从未构建）与集群侧 fsGroup 行为

### 🚀 性能与扩展性

- [ ] **资源限制** — Docker Compose `deploy.resources.limits` 已配置；JVM 堆内存 `-Xmx4g -Xms2g`（按实际调整）；Python worker 数 `WEB_CONCURRENCY=4`
- [ ] **连接池优化** — HikariCP `maximum-pool-size=20`（按负载调整）；Milvus 连接池 `MILVUS_POOL_SIZE=10`
- [ ] **向量索引参数** — Milvus HNSW `M=16, efConstruction=200`（默认值，超 100 万条数据需调优）
- [ ] **缓存预热** — 高频知识库元数据预加载；Prompt 模板缓存

### 📊 监控与告警

- [ ] **Prometheus + Grafana** — 导入 `deploy/monitoring/grafana/` 目录下的 dashboard；配置告警规则（CPU > 80%、内存 > 90%、磁盘 > 85%）
- [ ] **分布式追踪（Tempo）** — 监控栈已含 Tempo（OTLP 4318 接收 + Grafana Tempo 数据源自动装配）；`deploy/.env` 设 `TRACING_ENABLED=true` + `OTEL_ENABLED=true` + `OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4318/v1/traces` 后重启栈，一次问答的 Java→Python 调用链在 Grafana Explore → Tempo 可查
- [ ] **关键指标监控** — 文档解析成功率（目标 > 95%）、RAG 检索 P95 延迟（目标 < 500ms）、Agent 任务超时率（目标 < 5%）、用量配额告警（> 90%）
- [ ] **日志聚合** — ELK Stack 或 Loki + Grafana；关键错误日志告警（Slack/邮件/钉钉）
- [ ] **健康检查** — Java：`GET :9092/actuator/health`（独立管理端口，第十五轮 P0-8）；Python：`GET /health`；配置 Docker healthcheck 或 K8s liveness/readiness

### 🧪 测试验证

- [ ] **冒烟测试通过** — `.\scripts\smoke-test.ps1` 全部 PASS / 0 FAIL
- [ ] **E2E 测试通过** — `cd hfusionhub-frontend && npx playwright test`
- [ ] **压力测试** — 并发用户 100（JMeter/Locust）；文档上传→解析→检索链路稳定性；数据库连接池无泄漏

### 🔧 运维工具

- [ ] **备份恢复演练** — 模拟 MySQL 数据丢失 → 从备份恢复 → 验证数据完整性；模拟 Milvus 数据损坏 → 重建向量索引。MySQL 恢复脚本：`bash scripts/restore-mysql.sh <dump.sql.gz> --yes --dev`（演练，重建库→灌 dump→关键表核验；生产侧去掉 `--dev`）——2026-09-03 已在开发栈完成一次真实演练（78 表恢复，9 张关键表行数与恢复前一致）
- [ ] **日志轮转** — Docker 日志 `max-size: 100m, max-file: 3`；应用日志 Logback 每日切分（保留 30 天）
- [ ] **灾难恢复计划** — RTO（恢复时间目标）< 4 小时；RPO（恢复点目标）< 24 小时

### 📜 合规与文档

- [ ] **隐私政策** — 用户数据处理声明；Cookie 使用说明
- [ ] **API 文档** — Swagger UI 生产关闭或限制访问
- [ ] **运维文档** — 故障排查手册（[TROUBLESHOOTING.md](TROUBLESHOOTING.md)）、扩容步骤（[SCALING.md](SCALING.md)）

### ✅ 上线前最终确认

- [ ] 所有必需项（🔐 安全配置）已完成
- [ ] 在预生产环境运行 7 天无 P0/P1 故障
- [ ] 备份恢复流程已演练
- [ ] 监控告警已配置并测试
- [ ] 回滚计划已准备（Docker 镜像版本标记）

---

## 1. 架构速览（运维视角）

```
Internet ──> Ingress/FE(:80) ──> Java Backend(:8080) ──► Python AI(:9000)
                                            │                 │
                                            │            plugin-runner(:9100)
                                            │                 │
                                            │            (TLS) .──Docker Engine
                                            │                 │    (隔离、无 socket)
                                            ▼
                                     MySQL / Redis / Milvus
```

- **Java**：写路径（文档 / 会话 / Agent 编排）+ 配额账本 + SSE 转发。
- **Python**：RAG / Agent / 工具执行调度，只经内部 token 访问。
- **plugin-runner**：值得信赖的容器化沙箱，唯一连接"隔离 Docker Engine"的组件，
  绝不再挂载 `/var/run/docker.sock`。连不到引擎时 `/health` 返回 503（fail-closed）。

---

## 2. Runner TLS 证书：生成与轮换

### 2.1 为什么需要 TLS 证书

Runner 通过 `DOCKER_HOST` + `DOCKER_TLS_VERIFY=1` 访问独立 Docker Engine。
Compose 用 `deploy/runner-tls/{ca,cert,key}.pem` 作为 secrets 挂载到
`/certs/client/{ca.pem,cert.pem,key.pem}`；Helm 则把同三份内容放进名为
`pluginRunner.tlsSecretName` 的 Secret。**不要用 /var/run/docker.sock。**

### 2.2 首次生成

仓库提供重复可运行的脚本（自建 CA + 客户端证书，仅含 `clientAuth`）：

```bash
bash scripts/generate-runner-tls.sh deploy/runner-tls
# 产物：ca.pem / cert.pem / key.pem / ca-key.pem（CA 私钥，默认保留便于复签）
```

- 无本机 openssl 时可用容器替代：`docker run --rm alpine/openssl:3.3.0 ...`，
  或直接在能运行 openssl 的发布机 / CI 生成。
- **私钥（key.pem、ca-key.pem）绝不提交进仓库**。CI 的 `helm`/`docker-compose-validate`
  只做 `config -q` 与模板渲染，不校验文件真实性，因此切勿把真实证书放进 CI。

### 2.3 证书有效期与轮换

脚本签发有效期默认 825 天（CA 3650 天）。建议 **≤6 个月轮换一次**：

1. 重新生成（新 CN/新 key）：`bash scripts/generate-runner-tls.sh deploy/runner-tls`
2. 覆盖 Kafka/compose secrets 或 Kubernetes Secret：
   - Compose：覆盖 `deploy/runner-tls/*.pem` 后 `docker compose -f deploy/docker-compose.prod.yml up -d plugin-runner`
   - Helm：`kubectl create secret generic hfusionhub-runner-tls --from-file=ca.pem --from-file=cert.pem --from-file=key.pem -n <ns> --dry-run=client -o yaml | kubectl apply -f -`
3. 校验新的 client 证书与 CA 匹配：
   ```bash
   openssl verify -CAfile deploy/runner-tls/ca.pem deploy/runner-tls/cert.pem
   ```
4. 观察 Runner：`curl -fsS http://127.0.0.1:9100/health` 应返回 `docker_connected: true`。

> 轮换时 Engine 端 Server 证书（若有）也必须更新到同比 CA 链；若只换 client 证书，
> 需与 Engine 侧信任的 CA 保持同一签发者。

---

## 3. 插件镜像 digest：发布与登记

Runner 在执行前会用 **SHA-256 digest** 校验镜像（常量时间比较），防止拉取被替换。

### 3.1 发布一个插件镜像

1. 构建：`docker build -t hfusionhub-plugin-<name>:<tag> .`
2. 计算 digest：
   - 已推送的仓库镜像：`docker inspect --format='{{index .RepoDigests 0}}' <image>` → `... @sha256:<64 hex>`
   - 本地镜像：`docker inspect --format='{{.Id}}' <image>`（config digest，同样 `sha256:`）
3. 推送到 Runner 可访问的 registry（需路由放行）。

### 3.2 登记 digest

```sql
UPDATE plugin SET image_digest = 'sha256:<64 hex>', version = '<semver>'
WHERE plugin_id = '<uuid>';
```

Runner 在 `/execute` 时校验 `req.image_digest`，不匹配返回 400，插件不执行。
- digest 缺失 / 格式错误 → 400（必须先登记才能执行）。
- 换版本必须**同时**更新 `image_digest` 与 `version`，旧 digest 是刻意的 supply-chain 门禁。

### 3.3 审计

- `docker commit -a` 的镜像标签审计见 `/images` 端点（需 runner token）。
- 所有凭据校验 / 拒绝看 Runner 日志（`docker compose logs plugin-runner`）。

---

## 4. 配额账本排查

计量四张表（`V35__usage_ledger.sql`）：

| 表 | 用途 | 关键列 |
|----|------|--------|
| `usage_event` | 不可变追加日志 | `(tenant_id, meter, request_id, operation)` 唯一，保证幂等 |
| `usage_reservation` | 预占状态机 | `state ∈ {RESERVED, COMMITTED, RELEASED}`，单行/`(tenant,meter,request_id)` |
| `usage_counter` | 每日原子计数器 | `reserved` / `committed`，按 `(tenant,meter,window_key=YYYY-MM-DD UTC)` |
| `tenant_quota` | 租户配额覆盖 | 不填则回落 plan_tier 默认值 |

计量项（`meter`）：`chat_tokens | agent_tokens | index_chunks | plugin_executions`。

### 4.1 常见症状与查询

**症状 A：某租户突然 429 / 超额。**
```sql
SELECT meter, window_key, reserved, committed
FROM usage_counter
WHERE tenant_id = ? AND window_key = CURDATE();  -- 注意应用内部按 UTC
```

**症状 B：`reserved` 长期不回落（可能的预占泄漏）。**
```sql
SELECT meter, request_id, state, reserved_amount, created_at
FROM usage_reservation
WHERE tenant_id = ? AND state = 'RESERVED'
ORDER BY created_at DESC LIMIT 20;
```
恢复路径应把孤儿预占转 `RELEASED`；若仍有积压，参考 `DocumentIndexRecoveryScheduler` /
Agent 看门狗 `recoverAll` 的生命周期，必要时手动将 `state` 置 `RELEASED` 并补一条
`RELEASE` 事件（保持账本一致）。

**症状 C：后台任务跨 UTC 零点。**
结算/退回一律用**预占的 window_key**，不会在新一天错误扣减。若发现跨日对账不平，先核对
`usage_event.window_key` 与 `usage_reservation.window_key` 是否取自同一预占行。

### 4.2 幂等键（防重复扣费）

唯一键 `(tenant_id, meter, request_id, operation)` 使同一业务请求重放不重复记账。
检查重复：`SELECT operation, COUNT(*) FROM usage_event WHERE tenant_id=? GROUP BY request_id, operation HAVING COUNT(*) > 1;`

---

## 5. Agent 执行失败 / 租户拒绝 / Runner 不可达定位

### 5.1 Agent 状态机与错误码（`AgentConstants`）

终态：`succeeded | failed | cancelled | timed_out | dead_letter`。
可重试（来自 Python 映射或本地错误码）：`timeout/execution_timeout/connection_error/tool_error/internal_error`。
Python 语义 `completed/insufficient_evidence/timeout/tool_error/agent_failure` 会被收敛为契约终态。

**关键错误码**：
| 错误码 | 含义 | 处理 |
|--------|------|------|
| `tenant_unresolvable` | 队列路径无法解析归属租户 → **拒执行**、AI 零调用 | 检查 `agent_run→agent_task→user.tenant_id` 链路是否被删/孤儿 |
| `execution_timeout` / `watchdog_timeout` | 执行/看门狗超时 | 看 Python 侧日志与任务租约 |
| `superseded` | 被新 Run 取代 | 正常，无需处理 |
| `approval_expired` | 审批超时 | 评估审批期限配置 |

### 5.2 定位步骤（从上到下）

1. **状态与终态字段**：
   ```sql
   SELECT id, status, error_code, error_detail, tenant_id
   FROM agent_run WHERE id = <runId>;
   ```
2. **租户拒绝（tenant_unresolvable）**：核对
   ```sql
   SELECT run.tenant_id, task.tenant_id, user.tenant_id
   FROM agent_run run JOIN agent_task task ON task.id = run.task_id
   JOIN sys_user u ON u.id = task.user_id
   WHERE run.id = <runId>;
   ```
   三列为空则是归属链断裂，属配置/数据问题而非代码异常。
3. **Run 超时**：确认 `agent.run.timeout-seconds` 与租约 `lease-seconds` 配置，
   看 Python 侧是否在 `chat_stream` 完成后才发 `run_completed`。
4. **Runner / Engine 不可达**：
   ```bash
   curl -fsS http://127.0.0.1:9100/health   # 503 → Engine 不可达 / cert 不匹配
   ```
   - Runner 日志看 `docker_connected`、TLS 握手错误。
   - Python 侧若在发请求前先探测且 fail-closed，任务会直接失败而不是挂起。

### 5.3 工具审批 / 插件执行

- 高风险的写工具需审批；审批令牌状态 `none|issued|consumed|revoked`。
- 插件执行失败先看 `plugin_audit_log` 与 Runner `/execute` 返回的 `error_code`。

---

## 6. 安全回归（每日 / 每次发布）

完整清单见 `docs/SECURITY_REGRESSION.md`。核心：
租户隔离（X-Target-Tenant / 回调）、回调 HMAC 签名、插件沙箱 fail-closed、
quota ledger 幂等、Agent 不可解析租户拒绝执行五条。

## 7. 运营命令速查

```bash
# 起停 prod 栈
cd deploy && docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml down -v --remove-orphans

# 本机 Staging 演练（自动生成证书/.env + 全链路健康校验）
bash scripts/staging-rehearsal.sh
bash scripts/staging-rehearsal.sh --no-dind   # 无嵌套虚拟化时 runner 预期 503

# 健康端点
curl -fsS http://127.0.0.1:9092/actuator/health   # Java（独立管理端口）
curl -fsS http://127.0.0.1:9000/health                # Python
curl -fsS http://127.0.0.1:9100/health                # Runner（503=Engine 不可达）
```

## 相关文件

- `scripts/generate-runner-tls.sh`、`scripts/staging-rehearsal.sh`
- `deploy/docker-compose.prod.yml`、`deploy/helm/hfusionhub/`
- `V35__usage_ledger.sql`、`V31__plugin_image_digest.sql`、`V29__tool_plugin_sandbox.sql`
- `.github/workflows/ci.yml`（Helm 渲染 / compose 校验门禁）

---

## 8. 容灾手册：向量库（原 DR_VECTORS.md）

HFusionHub uses a dual-store architecture for document chunks:
- **MySQL** (`document_chunk` table): durable citation metadata (chunk_id, document_id, content_excerpt, outline_path, embedding_model/dimension/version)
- **Milvus** (standalone cluster in production): dense vector embeddings for similarity search

The MySQL chunk index is the **source of truth** for document ownership, citation integrity, and reconciliation. Milvus is rebuildable from the original documents; MySQL is not.

### 8.1 备份策略

**MySQL（主 — 每日、自动化）**
```bash
mysqldump -u root -p --single-transaction --routines --triggers \
  hfusionhub > hfusionhub_mysql_$(date +%Y%m%d_%H%M%S).sql

# Restore
mysql -u root -p hfusionhub < hfusionhub_mysql_YYYYMMDD_HHMMSS.sql
```

**Milvus（次 — 数据卷快照）**

数据卷实际名为 `<project>_milvus-data`（project = compose 文件所在目录名或 `COMPOSE_PROJECT_NAME`）。开发栈为 `docker_milvus-data`，生产栈（`deploy/docker-compose.prod.yml`）为 `deploy_milvus-data`。推荐直接用 `scripts/backup_milvus.sh` / `restore_milvus.sh`：

```bash
./scripts/backup_milvus.sh [backup_dir]
./scripts/restore_milvus.sh <backup_file.tar.gz>
```

手动等价命令：

```bash
# Stop Milvus briefly for consistent snapshot
docker compose -f deploy/docker-compose.prod.yml stop milvus

# Snapshot the data volume
docker run --rm -v ${COMPOSE_PROJECT_NAME:-deploy}_milvus-data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/milvus_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Restart Milvus
docker compose -f deploy/docker-compose.prod.yml start milvus
```

**Cluster mode: co-store JSON is not used**
Production / staging run in `VECTOR_STORE_MODE=cluster`. BM25 and citations
read their scoped corpus directly from Milvus via `all_chunks()`; there is no
per-pod `chunks_store.json`, so no separate co-store backup is required.

**Lite dev mode (bare-metal only): co-store JSON only**
`VECTOR_STORE_MODE=lite` 仅用于本地裸跑（无 Docker）与测试。此时 `python-ai/data/chunks_store.json`
本地 co-store 会被读写，可作为普通文件直接拷贝备份：

```bash
cp python-ai/data/chunks_store.json backups/chunks_store_$(date +%Y%m%d_%H%M%S).json
```

### 8.2 恢复流程

**Scenario 1: Milvus data loss, MySQL intact**
1. Milvus volume is corrupt or deleted.
2. MySQL `document_chunk` table has all metadata (embedding_model, embedding_dimension, embedding_version).
3. **Action**: Drop and recreate the Milvus collection. Re-index affected documents from their source files via the Java API.

```bash
# Force collection drop
export MILVUS_ALLOW_COLLECTION_DROP=true
# Trigger re-index for affected documents via the UI or API:
#   POST /api/vectorize/{documentId}/start
```

**Scenario 2: MySQL chunk data loss, Milvus intact**
1. `document_chunk` table is empty or corrupt.
2. Milvus has the vectors but no citation metadata.
3. **Action**: Rebuild MySQL from Milvus query results (chunk_id, document_id, knowledge_base_id, content). Content excerpts are in Milvus `content` field. This is a partial recovery — outline_path and metadata may be incomplete.

**Scenario 3: Both stores lost**
1. Full rebuild from source documents.
2. Restore MySQL from backup if available, then re-index all documents.

**Scenario 4: Orphan vectors detected (reconciliation failure)**
1. Run `VectorReconciliationService.reconcileAll()` via admin endpoint or scheduled job.
2. Orphan vectors (in Milvus but not MySQL): safe to delete — they serve no citation purpose.
3. Missing vectors (in MySQL but not Milvus): re-index the affected documents.

### 8.3 索引版本控制

Every indexing run produces a unique `index_version` (UUID). This is stored in:
- `document_index_job.index_version`
- `document_chunk.index_version`
- Milvus chunk metadata

Stale callbacks from superseded workers are rejected by matching `index_version`.

When the embedding model or dimension changes:
1. Set a new `embedding_version` (e.g., `v2`) in the Python config.
2. Re-index all documents — old chunks are automatically superseded.
3. The `embedding_model`, `embedding_dimension`, and `embedding_version` columns on `document_chunk` track provenance per chunk.

### 8.4 对账命令

**Check a single document**
```bash
curl -H "X-Internal-Token: $PYTHON_AI_INTERNAL_TOKEN" \
  http://localhost:9000/api/chunks/{documentId}?page=1&size=100000
```

**Compare with MySQL**
```sql
SELECT chunk_id, document_id, embedding_model, embedding_dimension
FROM document_chunk
WHERE document_id = {documentId}
ORDER BY chunk_index;
```

**Delete orphan vectors**
```bash
# Via the vectorization API
curl -X DELETE -H "X-Internal-Token: $PYTHON_AI_INTERNAL_TOKEN" \
  http://localhost:9000/api/documents/{documentId}/chunks
```

### 8.5 向量库环境变量参考

| Variable | Default | Description |
|---|---|---|
| `VECTOR_STORE_MODE` | `lite` | `lite`（代码默认，仅本地裸跑/测试）或 `cluster`（Docker/生产，推荐） |
| `SERVER_ENV` | `development` | `production`/`staging`/`development` |
| `MILVUS_HOST` | `localhost` | Milvus standalone host |
| `MILVUS_PORT` | `19530` | Milvus standalone port |
| `MILVUS_LITE_PATH` | `./milvus_data.db` | 仅 `VECTOR_STORE_MODE=lite` 时的嵌入式 Lite 文件路径 |
| `MILVUS_ALLOW_COLLECTION_DROP` | `false` | Safety gate for destructive ops |
| `EMBEDDING_MODEL` | `unknown` | Current embedding model name |
| `EMBEDDING_DIMENSION` | `1024` | Vector dimension |

### 8.6 向量库监控

- **Prometheus metrics**: `python_ai_vector_store_insert_total`, `python_ai_vector_store_search_total`
- **Alert rules**: `deploy/monitoring/alert_rules.yml` — vector store errors, high latency, reconciliation failures
- **Health check**: `GET /health` on Python AI service (returns Milvus connection status)

---

## 9. Isolated Engine Rehearsal

Run the full local rehearsal only with a disposable `docker:dind` Engine. The
runner receives TLS client files as Compose secrets; it never receives the host
Docker socket. The certificate generator now creates both the Compose files
(`ca.pem`, `cert.pem`, `key.pem`) and the `dind-certs/{server,client}` layout.

```powershell
# Windows. If the host proxy is v2rayN on 127.0.0.1:10808, pass it explicitly.
powershell -ExecutionPolicy Bypass -File scripts/staging-rehearsal.ps1 `
  -DindProxy http://127.0.0.1:10808

# Expected: exit 0 and Runner health reports docker_connected:true.
# Fail-closed control: expected exit 3 and Runner health returns HTTP 503.
powershell -ExecutionPolicy Bypass -File scripts/staging-rehearsal.ps1 -NoDind
```

```bash
# Linux/macOS equivalent. DIND_PROXY is optional and is translated from
# localhost to host.docker.internal for the nested daemon.
bash scripts/staging-rehearsal.sh --dind-proxy http://127.0.0.1:10808
bash scripts/staging-rehearsal.sh --no-dind
```

The rehearsal injects the Dind endpoint only into the Compose process. It does
not persist a local or production `PLUGIN_RUNNER_DOCKER_HOST` in `deploy/.env`.
This prevents a `--no-dind` validation run from accidentally contacting an
existing Engine.

After the exit-0 rehearsal, run the runtime boundary checks:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/plugin-e2e-acceptance.ps1
```

The acceptance script builds `hfusionhub-plugin-acceptance:v1` in the isolated
Engine and verifies valid and invalid digests, image allowlist enforcement,
CPU/memory/PID/read-only limits, plus an allowed and blocked in-engine network
probe. It removes its temporary HTTP server and image unless `-KeepImage` is
specified. Approval-token and quota reserve/settle remain tenant-bound
application contracts and are verified by the Java/Python test suites rather
than synthetic requests without a tenant, plugin record, and agent run.

## 10. 卷属主与运行身份

容器写不写得进卷，取决于两件事是否对齐：**进程身份**（uid/gid）与**卷属主**。第八十四批
之前两侧都没约定过：应用镜像用 `useradd -r` / `adduser -S` 建用户（号由基镜像当时占了
哪些号决定，系统池 100–999，重建即漂移），helm 里除 plugin-runner 外没有任何
securityContext，也没有 fsGroup。现在三处钉成同一个号，由门禁核对：

| 位置 | 键 | 号 |
| --- | --- | --- |
| `deploy/Dockerfile.python` | `groupadd -g` / `useradd -u` | 10001 |
| `deploy/Dockerfile.java` | `addgroup -g` / `adduser -u` | 10001 |
| `deploy/helm/hfusionhub/values.yaml` | `podSecurity.runAsUser` / `runAsGroup` / `fsGroup` | 10001 |

- 门禁：`python scripts/static-checks.py --container-uid`（已并入默认全跑档）；红→绿的
  两种漂移形态（某处换了号、fsGroup 与 runAsGroup 不同号）由
  `python-ai/tests/test_container_identity.py` 钉住。
- `fsGroup` 是关键项：空 PVC/空命名卷的属主由 provisioner 决定，镜像里的 `chown` 会被
  挂载后的卷内容取代；有了与 runAsGroup 同号的 fsGroup，kubelet 会把卷交给这个组，
  java 与 python（2 副本）才能在同一块 RWX uploads 卷上互写。
- 镜像同时创建自己要挂载的目录（`/app/uploads`、java 侧同路径），这样 compose 的命名卷
  首次初始化时就继承正确属主。
- plugin-runner 用独立的 1000：镜像里 `useradd` 未钉 `-u`，所以号写在 chart 里（遗留项）。

### 10.1 升级到钉死 uid 的一次性修复

改动之前建下的卷，其内容属主仍是旧的系统号，新容器以 10001 启动后写旧文件会 `EACCES`。
选一种执行（都需要一个停机窗口）：

```bash
# compose：命名卷逐个 chown（卷名前缀是 compose 项目名，用 docker volume ls 确认）
docker run --rm -v <project>_uploads-data:/v alpine:3.20 chown -R 10001:10001 /v
docker run --rm -v <project>_python-data:/v  alpine:3.20 chown -R 10001:10001 /v
```

```yaml
# helm：给每块 PVC 各跑一次这个 Job（claimName 换成 <rel>-uploads-pvc / <rel>-audit-pvc）
apiVersion: batch/v1
kind: Job
metadata:
  name: fix-volume-ownership
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: chown
          image: alpine:3.20
          command: ["sh", "-c", "chown -R 10001:10001 /v"]
          volumeMounts:
            - {name: vol, mountPath: /v}
      volumes:
        - name: vol
          persistentVolumeClaim:
            claimName: hf-uploads-pvc
```

### 10.2 实测（第八十八批：docker 侧已跑，集群侧仍未跑）

本批第一次有可用的 docker 引擎，`deploy/Dockerfile.python` 从引入至今**首次真实构建成功**
（linux/amd64，镜像 `hfusionhub/python88:rc`）。构建过程本身结掉了第 12 节的三个锁缺陷：
前两次构建分别死在 `pywin32`（1706 秒前的 collect）、无哈希的 OTel 裸 pin、以及
`uvloop!=0.15.0,!=0.15.1,>=0.14.0`（2582 秒，collect 末尾）；修好后 `Successfully installed
… uvloop-0.23.0 …`，`arq`/`redis` 两条锁外钉版随后装进同一层。

**验证用的是 `Dockerfile.validate`**（`deploy/Dockerfile.python` 的副本，差异只有两处、都写在
文件头注释里）：`ENV PIP_DEFAULT_TIMEOUT=120`，以及把三条 `pip install --no-cache-dir` 换成
`RUN --mount=type=cache,target=/root/.cache/pip`。原因不是镜像有问题，是宿主的下载面——
aliyun 镜像实测 23–60 kB/s，pip 默认 15 秒读超时在拉 uvloop 那个 4 MB wheel 到 0.3 MB 时
`TimeoutError: The read operation timed out`（第 3 次构建即死在此，2964 秒）。这两处都不改
被验收的那份 Dockerfile 的语义，但**上线用的镜像仍是 `--no-cache-dir` 的那一份**，它在慢网
上的首次构建同样会遇到这条超时；已在 10.3 记为未收口。

已实测到的四条（`hfusionhub/python88:rc` + 三个空命名卷）：

| 编号 | 断言 | 实测结果 |
| --- | --- | --- |
| M0 | 运行身份与"锁外钉版没把锁里版本拖下去" | `User=hfusionhub WorkDir=/app`；`arq==0.26.3`、`redis==5.3.1`、三条 OTel `==1.45.1`、`protobuf==7.35.1`（未被 1.29.0 的 `protobuf<6.0` 拖低）、`pymilvus==3.0.0` |
| M1 | 空命名卷的挂载点属主来自镜像内容，且 uid=10001 写得进 | `/app/uploads`、`/app/eval-harness`、`/app/audit-queue` 三条均 `uid=10001 gid=10001 mode=755` + `WRITE_OK`，`mkdir -p /app/uploads/documents` 成功 |
| M2 | 保留口径在真卷上按 mtime 淘汰、`protect` 不占名额 | 6 组真产物（`runner.new_run_file` + `report.save_report`）→ `prune_runs(keep=2, protect=最新)` 删掉最旧 3 组 run 与其 `_report.md`，`skipped=[]`，剩 3 组 = keep 2 + protect 1 |
| M4 | 卷属主还是 root 时的失效样子（10.1 的一次性 chown 的依据） | 写：`PermissionError: [Errno 13]`；`prune_runs(keep=0)` **不抛**，两条记进 `skipped` 并各打一行 `[eval-harness] retention: cannot remove …`，文件留在盘上 |

**一个"看起来通过、其实没验证"的陷阱**：在 Git Bash 里跑探针时，MSYS 会把形如
`key=/path` 的参数值改写成宿主路径，实测 `-e EVAL_HARNESS_DATA_DIR=/app/eval-harness` 进到
容器变成 `D:/college/Git/app/eval-harness`——POSIX 下这是**相对**路径，产物于是落进容器可写层，
而探针照常打印"删除 3 个、跳过 0 个"。修法是 `export MSYS2_ARG_CONV_EXCL='*'`（老 msys 用
`MSYS_NO_PATHCONV=1`），并让探针自己断言：目录必须绝对、且从 `/proc/self/mounts` 里查得到
`/app/eval-harness` 这条挂载，否则 `SystemExit(2)`。任何"往容器里传路径"的核对都该带这条自证。

helm 侧仍未跑（本机无集群）：渲染层证据是第八十四批那份（22 个对象、java/python 的
podSecurityContext 三项齐、0 个 `<no value>`），"真的能写"要在真实环境各跑一次：

```bash
kubectl -n <ns> exec deploy/<rel>-python -- sh -c 'touch /app/uploads/.writable /app/audit-queue/.writable && echo ok'
kubectl -n <ns> exec deploy/<rel>-java   -- sh -c 'mkdir -p /app/uploads/documents && echo ok'
# compose 侧等价物
docker compose exec python-ai sh -c 'touch /data/uploads/.writable && echo ok'
```

跨服务的那一条要成对做（写的一方与读的一方都不是同一个进程）：

```bash
docker compose exec java-backend   sh -c 'mkdir -p /app/uploads/documents && echo from-java > /app/uploads/documents/.probe'
docker compose exec python-ai      sh -c 'cat /app/uploads/documents/.probe && touch /app/uploads/documents/.from-python && echo ok'
```

`python-ai` 读不到就是 10.4 的契约没落地（挂载或 root 缺一处），Java 侧的解析会一律
回 `文件不存在或不在允许的上传目录中`（code 10001）。**这两条本批都没做**：M1 里的
`mkdir /app/uploads/documents` 是 python 容器自己建的，java 镜像至今未构建过。

### 10.3 已知未收口

- **"同路径互见"只做到了配置层对齐 + 单侧可写**：10.2 的 M1 只证明 python 那侧写得上，
  java 镜像从未构建（`Dockerfile.java` 的 `adduser -u 10001` 与 `/app/uploads` 创建按 Alpine
  的 `adduser` 参数形态写，第一次真实构建即是验收），"java 写、python 读"仍要在起得来的
  栈里做一次（10.2 末尾的命令对）。
- **慢网上的首次构建**：`--no-cache-dir` ＋ pip 默认 15 秒读超时，在 23–60 kB/s 的镜像源前会
  随机死在大 wheel 中途；验证副本把超时提到 120 秒并改用 cache mount 才走通。生产 Dockerfile
  是否要收这个调整，取决于构建环境，本批不动它。
- **`UPLOAD_DIR` 与 `DOCUMENT_STORAGE_ROOT` 是两个不同的根**：前者是 python 自己的暂存/摄取
  目录（compose 指 `/data/uploads`，进 `python-data`），后者是"允许解析 Java 文件"的围栏根。
  看到两者不一致不代表配置错了，但它们各自挂哪个卷必须与挂载表一致。
- plugin-runner 镜像 uid 未钉 `-u`，1000 只写在 chart 里。
- mysql/etcd/milvus/redis 仍无 pod securityContext（上游镜像以 root 起、入口脚本自 chown）。

### 10.4 文档目录的同路径契约（第八十五批）

Java 与 python **必须**在同一个绝对路径上看见同一个文件，这不是可选优化：

1. Java 把 `user.dir`(=运行阶段 WORKDIR `/app`) 下的绝对路径写进 `document.file_path`
   （`DocumentServiceImpl.java:64` 的 `UPLOAD_DIR = "uploads/documents"`，`:528-529` 拼成绝对路径）；
2. `VectorizationServiceImpl.java:737` 把它原样发给 python 的 `/api/parse`；
3. python 只接受**自己容器里真实存在**、且在 `DOCUMENT_STORAGE_ROOT` 之下的路径
   （`validators.py:87-103`：`resolve(strict=True)` + `relative_to`，否则 400 code 10001）；
4. 反向同构：`/api/ingest/url` 返回的 `file_path` 由 Java 持久化（`DocumentServiceImpl.java:194-204`）
   并回写正文，所以 python 的写入点也必须落在 Java 挂的那块卷上。

⇒ 每个 python 工作负载都要**成对**具备：`DOCUMENT_STORAGE_ROOT=/app/uploads/documents`
＋ 共享 uploads 卷挂在 `/app/uploads`（或其祖先）。

| 部署面 | root | 挂载 | 状态 |
|---|---|---|---|
| prod compose | `deploy/docker-compose.prod.yml:249` | `:276` `uploads-data:/app/uploads` | 成对 |
| helm | `templates/python.yaml:73-74` | `uploads-pvc` → `/app/uploads` | 成对 |
| dev compose `python-ai` / `python-ai-worker` | 本批补齐 | 本批补齐 | 此前两处都缺 ⇒ 容器化一键启动下每次解析 400 |
| 宿主开发态（`mvn spring-boot:run` + venv） | 镜像默认值 `../java-backend/uploads/documents` | 同一台机器同一文件系统 | 默认值就是为它设计的 |

期望路径不是硬编码：`scripts/static-checks.py` 检查 9（`--document-storage-root`，已并入全跑档）
从 `Dockerfile.java` 的运行阶段 WORKDIR 与 `DocumentServiceImpl.java` 的 `UPLOAD_DIR` **派生**，
任一侧改动都会让三档同时报红。回归测试见 `python-ai/tests/test_upload_path_contract.py`。

## 11. 评测产物的落点（第八十六批）

评测中枢的 `runs/`、`reports/`、`scores` 与 judge 缓存此前是三处模块级硬编码的**相对**目录
（`app/api/eval_harness.py:31`、`app/core/eval_harness/runner.py:25`、
`app/core/eval_harness/metrics/llm_judge.py:63`）。容器里 `WORKDIR=/app` ⇒ 落 `/app/data`，
而三档 shipped 拓扑没有一档把卷挂在那儿（compose 只挂 `/data`，helm 连 `/data` 都不存在）。
后果不是"少一个优化"而是功能本身不可用：`/score`、`/slides`、`/report`、`/diff` 四个端点是
按"文件还在"读回的（`eval_harness.py:211/220/236-237`），容器或 Pod 一重建就全部 404，
helm 两副本下副本 A 生成的报告对副本 B 根本不可见。

### 11.1 现在的落点

两把键都可配（`app/utils/config.py:180-182`），默认值保持宿主开发态的相对布局：

| 部署面 | `EVAL_HARNESS_DATA_DIR` | `EVAL_JUDGE_CACHE_PATH` | 卷 |
|---|---|---|---|
| dev compose `python-ai` | `/data/eval-harness` | `/data/eval-judge-cache.http.json` | `python-data:/data` |
| dev compose `python-ai-worker` | `/data/eval-harness` | `/data/eval-judge-cache.worker.json` | `python-data:/data` |
| prod compose `python-ai` | `/data/eval-harness` | `/data/eval-judge-cache.json` | `python-data:/data` |
| helm `python`（2 副本） | `/app/eval-harness` | `/app/eval-harness/$(POD_NAME)/judge_cache.json` | `<rel>-eval-pvc`（RWX，`pythonAi.evalReportsSize`=2Gi） |
| 宿主开发态 | 默认 `data/eval_harness` | 默认 `data/eval_harness/judge_cache.json` | 直接落仓库目录 |

### 11.2 为什么两条规则方向相反

- **产物该共享**：一个 run 文件写一次，之后 `/diff`、`/report`、`/slides` 只按文件名读回，
  没有并发写同一文件的场景 ⇒ 跨 Pod 可见是需求，helm 必须 RWX。
- **judge 缓存不该共享**：读写缓存是整文件 read‑modify‑write（`llm_judge.py:73` 起），
  两个进程共用一个文件 = 后写者丢弃先写者的条目，没有任何告警。所以它刻意与共享根**分面**：
  compose 每进程一个文件，helm 落在同一块 RWX 卷上但按 `$(POD_NAME)` 分子目录。
- 代价如实记着：**缓存按 Pod 分之后，跨 Pod 不命中**，同一问题在两个副本上会各判一次分（多花
  一次评审调用），换来的是不会静默丢缓存。若要真共享缓存，得换成键值存储而不是一个 JSON 文件。

### 11.3 保留口径（第八十七批）

第 86 批把产物搬上卷之后，失效方式从"重建即丢"换成"卷被写满"：一个 run 的 JSONL 逐样本
存召回全文（`EvalRecord.contexts`，`app/core/eval_harness/schemas.py:44`），一次评测最多
500 条样本、每条最多 top_k 篇原文，而 2Gi 的 eval PVC 一旦写满，同卷的其它写者会一起失败。

- **口径是数量，不是天数也不是字节**：`EVAL_RETENTION_KEEP`（默认 50）约束"旧的留几组"，
  一组 = `<label>_<ts>.jsonl` 与它派生的 `_scores.json`/`_report.md`/`_slides.html`
  （命名由 `run_file.replace(".jsonl", …)` 决定，四处读回的端点都按这个名字找）。
- **淘汰与 `/runs` 同源**：`retention.prune_runs` 复用 `runner.list_run_files` 的顺序，
  所以"被删掉的那条"与"控制台认为最新的那批"永远是同一套判断，不会删掉界面还在列的文件。
- **触发点是 `/run` 收尾**（`app/api/eval_harness.py` 的 `start_run`，产物写齐之后、
  Java 摘要回调之前，走 `asyncio.to_thread`）。没有后台任务，也没有一个等着运维点的清理
  端点：本仓已有 `checkpoint.prune`（`app/core/agent/checkpoint.py:220`）与
  `approval_store.cleanup_expired`（`app/core/agent/approval_store.py:153`）两个**零调用方**
  的清理函数，再加第三个不会更安全。
- **本次那条受保护且不占名额**：时间戳是秒级，同秒两条时它未必排在最前，故显式 `protect`；
  因此盘上最多 `keep+1` 组。`keep=0` 的含义是"只留本次"。
- **孤儿派生产物一并删**：对一条旧 run 手动 `POST /score` 会重建它的报告文件，若只按 run
  文件淘汰，这些没有对应 run 的文件永远清不掉。
- **两副本在同一块 RWX 卷上并发清扫是预期行为**：对手副本先删掉某个文件不算故障
  （`FileNotFoundError` 被吞、不计入本次的 `deleted_*`），删不掉的（权限/IO）记进
  `skipped` 并告警，清扫失败不会把一次已完成的评估判失败。

三处不在保留口径内，如实记着：

- **judge 缓存不受这个口径管理**：它不按 run 生长（每个被评审的 case 一条），但也**没有任何
  淘汰**，`EVAL_JUDGE_CACHE_PATH` 会随评测次数单调变大；处理它要换键值存储而不是加计数器。
- **Java 摘要行不删**：`_notify_java_record` 写进 `eval_harness_runs` 的行会活得比明细文件
  久（该表在仓内**没有读点**，所以留下的是无害的聚合摘要而不是 404；它的 `run_file` 上还有
  `uk_eval_harness_run_file` 唯一索引，见 `V79__eval_harness_runs.sql:23`）。
- **没有按字节/按天数的上限**：`keep` 是唯一旋钮，`evalReportsSize` 与它之间没有联动，
  把卷调大只靠运维自己放宽 `EVAL_RETENTION_KEEP`。

### 11.4 未收口

- **RWX 是否真能拿到，取决于 storage class**：本仓没有声明 StorageClass，`ReadWriteMany`
  请求在只支持 RWO 的提供方上会以 `Pending` 表现，而不是渲染期报错。
- **两把键在 import 时绑定**（模块级常量），改了环境变量必须重启进程才生效。
- 11.1 的表仍是渲染层与文本层证据（三档拓扑没有起过任何一个）。但**落点与读回这条链在
  真实容器上跑通了**（第八十八批，`hfusionhub/python88:rc` + 命名卷挂 `/app/eval-harness`）：
  一个容器用 `runner.new_run_file` + `report.save_report` 写 6 组产物、`prune_runs` 删到
  keep=2＋protect，**换一个全新容器**挂载同一块卷后 `GET /api/eval-harness/runs` 列出残留的
  3 条（含 `size_bytes` 与 `modified_at`），`GET /api/eval-harness/report?run_file=<最新之一>`
  取回报告正文，缺 `X-Internal-Token` 的那一次回 **401**。也就是"卷上的文件还在 ⇒ 端点读得回"
  不是推断而是实测；仍未跑的是**一次真评测**（要模型与 Java 检索在场），以及两副本在同一块
  RWX 卷上并发 `/run` 的清扫竞争（11.3 最后一条只有测试层的证据）。有集群时的口径：

```bash
kubectl -n <ns> exec deploy/<rel>-python -- sh -c 'touch /app/eval-harness/.w && echo ok'
# 跑一次小样本评测，删掉 Pod，再用新 Pod 读回同一份报告
curl -s -X POST http://<svc>/api/eval-harness/run -H "X-Internal-Token: …" -d @run.json
# 保留口径生效与否的可核对证据：日志里这条只在真删了东西时出现
# [eval-harness] retention keep=… runs=… artifacts=… skipped=… dir=…
```

## 12. 依赖锁的可安装面（第八十八批）

`python-ai/requirements.txt` 是 `pip-compile --generate-hashes --allow-unsafe` 的产物。
它有三个**只在别的机器上才发作**的失效方式，开发机（Windows）一个都看不见：

| 规则 | 破坏后的表现 | 第一次被发现的方式 |
| --- | --- | --- |
| 凡上游只在 Windows 上需要的包（`pywin32`、`win32-setctime`），锁里必须带 `sys_platform == "win32"` | linux/amd64 上 `Could not find a version that satisfies the requirement pywin32==312 (from versions: none)`（PyPI 上 pywin32 只有 win32 wheel、无 sdist） | 第八十四批把"首次真实构建即是验收"写进 10.2，本批第一次真跑构建即死在此 |
| 锁内条目要么全带 `--hash=`，要么全不带 | pip 在**任一**条目带哈希时自动进入 `--require-hashes`，把其余裸 pin 整体拒绝（任何平台都失败） | 修完上一条后同一次构建再往前走 1706 秒，死于 `opentelemetry-api==1.29.0` 缺哈希 |
| 凡上游在**非** Windows 上才需要的包（`uvicorn[standard]` 的 `uvloop`），锁里必须有它的 `==` pin ＋ 排除 win32 的 marker | 哈希模式不接受 extra 自带的 `>=` 规格：`In --require-hashes mode, all requirements must have their versions pinned with ==. These do not: uvloop!=0.15.0,!=0.15.1,>=0.14.0` | 修完前一条后同一次构建走到 collect 末尾（2582 秒）才报，代价是"锁修好了但镜像仍然装不上"要多花一整次构建才知道 |

第三条与第一条同根、方向相反：锁是在 Windows 宿主上无 `--python-platform` 编译的，
pip-compile 按 marker 为假直接把 `uvloop` 跳过（PyPI 上 uvicorn 0.27.0 的 `standard` extra
原文是 `uvloop!=0.15.0,!=0.15.1,>=0.14.0; (sys_platform != 'win32') and (sys_platform !=
'cygwin' and platform_python_implementation != 'PyPy') and extra == 'standard'`），而 extra
的另外 7 个依赖（click / h11 / httptools / python-dotenv / pyyaml / watchfiles / websockets）
在 Windows 上不过滤，全都进了锁。所以"只看 diff 里有没有 uvloop"是不可能的——它不是被删了，
是**从来没出现过**。修法照 pip-compile 在 Linux 上会产出的形状：
`uvloop==0.23.0 ; sys_platform != "win32" and sys_platform != "cygwin" and
platform_python_implementation != "PyPy"` ＋该版本 61 个文件（60 wheel + sdist）的 sha256
升序，插在 `uvicorn[standard]` 块之后，两份锁各一条。marker 必须留着，否则生成锁的那台
Windows 宿主自己装不上它。

历史线：`3cd5303` 当年用的 `RUN sed 's/uvicorn\[standard\]/uvicorn/g'`（今天仍活在
`docker/Dockerfile.plugin-runner:12`）绕的正是这个洞，代价是镜像里没有 uvloop/httptools；
`b69b0178` 以"`--require-hashes` 已不再使用"为前提撤掉 sed 并恢复 `[standard]`——那个前提是
错的（第一条与第二条都建立在它自动开启之上），而撤掉之后这份 Dockerfile 再没被真实构建过
（直到本批，10.2），所以洞藏到了本批。

顺带暴露的一个盲点：`name[extra]==ver` 形态的条目原先**两套锁解析器都看不见**（包名正则不含
`[`），prod 锁实际 77 条只数出 74、dev 锁 102 条只数出 97 ⇒ 一个手工追加的无哈希
`foo[bar]==1.2.3` 恰好落在门禁与测试共同的盲点上。正则已修。

**这类缺陷是两份锁一起坏的**，因为 `requirements-dev.txt` 由 `requirements-dev.in:4` 的
`-r requirements.in` 编译，出自同一次单平台 pip-compile：本批实测两份锁里的 `pywin32` /
`win32-setctime` **都没有 marker**（`requirements-dev.txt:1386/2082`），`uvloop` **两份都缺**。
而 CI 的 python job 装的是 dev 锁（`ci.yml:155`、`ci.yml:178`、`plugin-security.yml:21`、
`eval-nightly.yml:168`，全部 `ubuntu-latest`），镜像装的是 prod 锁（`deploy/Dockerfile.python:16`）——只修前者，
CI 照旧死在同一行。所以门禁核的是 `LOCK_FILES` 两份都核。按同一机制，9 处
`pip install -r requirements*.txt`（`ci.yml:155/178/215/327`、`e2e.yml:61/200`、
`eval-nightly.yml:76/168`、`plugin-security.yml:21/164`）在 CI 上都应当死于 uvloop 这一行——
**这是从构建日志的机制推出来的，本机没有跑过 CI，没有实测**。

第二条可在数秒内复现，不必等一次完整构建（两份文件放一起，第二条没有哈希）：

```bash
printf 'idna==3.18 \\\n    --hash=sha256:7f952cbe720b688055e3f87de14f5c3e5fdaa8bc3928985c4077ca689de849a2 \\\n    # via requests\nopentelemetry-api==1.45.1\n' > /tmp/mixed.txt
pip install --dry-run --no-deps -r /tmp/mixed.txt
# ERROR: Hashes are required in --require-hashes mode, but they are missing from some
#        requirements. …（If you did not enable --require-hashes manually, note that it
#         turns on automatically when any package has a hash.）
```

### 12.1 两个"锁外钉版"的例外，以及它们为什么在锁外

`deploy/Dockerfile.python` 里有两条 `pip install "x==y"`（arq、opentelemetry 三条），它们
**不在** `requirements.txt` 里。这不是随意加的，是两处已知债：

- **arq**：`requirements.in:21` 有 `arq>=0.26`，但现锁里既没有 `arq` 也没有 `redis`——锁与
  `.in` 早已分叉，Dockerfile 的显式钉版是让它进镜像的唯一途径。
- **opentelemetry**：`65b3ef8b`（2026-09-04）手工把三条裸 pin 追加到锁尾，就是上表第二条
  的破坏形状。补哈希并不够——它的 closure（`opentelemetry-proto`、`-semantic-conventions`、
  `-exporter-otlp-proto-common`、`googleapis-common-protos`、`deprecated`）一个都不在锁里，
  而哈希模式要求**全部**传递依赖一起钉死。真要做是一次完整重编译，而那次重编译必须同时
  决定 arq/redis 的归属，本批不夹带。
- 版本不能停在 `1.29.0`：`opentelemetry-proto 1.29.0` 要 `protobuf<6.0`，与锁里的
  `protobuf==7.35.1`（`# via pymilvus`）冲突，装它会往下拖 protobuf。现在钉 `1.45.1`
  （其 proto 放宽到 `<8.0`，`requires-python>=3.10` 与镜像的 3.11 相符）。

**连带后果**：OTel 只在镜像里、dev 锁里没有 ⇒ CI 的环境上它永远不可用。因此直接
`from opentelemetry import …` 的用例必须自带"环境不具备则跳过"的前提，否则 dev 锁的 marker
一修好，CI 第一次走到 pytest 就红在那里（`tests/test_trace_middleware.py` 的
`TestOtelTraceparentPropagation` 用 autouse fixture `importorskip` 声明这一点；实测：装了
OTel 12 passed，假装没装则 10 passed + 2 skipped）。这条覆盖真正被执行的位置是镜像内。
同理 `requirements-dev.txt` 里也没有 `arq`，但 `app/core/tasks/queue.py:77` 与
`arq_tasks.py:24` 都是函数级导入，缺包不影响导入面。

### 12.2 防回潮

- 门禁：`python scripts/static-checks.py --requirements-markers`（检查 11，已并入默认全跑档），
  纯文本核对，不需要 docker 或网络。它核三件事：Windows-only 条目带 marker、**非 Windows
  专属条目存在且 marker 排除了 win32**（反向清单 `NON_WINDOWS_ONLY_PINS`，新增此类依赖时与
  `WINDOWS_ONLY_PINS` 一起同步）、锁的哈希形态一致。
- 测试：`python-ai/tests/test_requirements_platform_markers.py` 钉住解析器口径（含
  `name[extra]==ver` 形态必须被解析出来、且两套解析器条目数一致）、上面三条规则、uvloop 的
  哈希集覆盖 `python:3.11-slim` 实际挑中的那个 wheel、钉住的版本落在 extra 自己的
  `!=0.15.0,!=0.15.1,>=0.14.0` 里，以及"OTel 只能由一处声明（锁 或 Dockerfile）"和
  "两处都没有 ⇒ 追踪静默关闭"。
- 第三条没有便宜的复现命令：pip 在哈希模式下要为每个候选文件取哈希，`pip install --dry-run`
  在 linux 容器里一样要把锁里的 wheel 下下来（本批实测跑到 10 分钟仍未走完 collect），所以
  "秒级复现"只适用于第二条那个形状（混不混哈希在本地就能判）。第三条靠纯文本报门禁。
- 重新生成锁的命令写在 `requirements.in:2`。**注意直接对现锁跑它会静默删掉任何不在 `.in` 里
  的条目**（本批对照实验：原样 `.in` 编译成功，产物没有 OTel，并新增 `arq==0.28.0` +
  `redis[hiredis]==5.3.1`，与现锁 diff 174 行）。

### 12.3 未收口

- **CI 上的结果本批没有跑过**：`ci.yml:327`、`e2e.yml:61/200`、`eval-nightly.yml:76`、
  `plugin-security.yml:164` 装 prod 锁，`ci.yml:155/178`、`plugin-security.yml:21`、
  `eval-nightly.yml:168` 装 dev 锁。两条锁的 marker 都已修，本批只有本地镜像与秒级复现
  的证据，CI 要等下一次 run 才算验收。
- **锁仍然不是跨平台锁**：marker 只补在两个 Windows-only 条目加一个非 Windows 专属条目上，
  其余条目仍是单平台编译产物；`uvloop` 这一条是靠读上游 metadata（PyPI 的 `requires_dist`）
  才发现的，不是靠"在另一个平台编译一次"。正解是用 `--python-platform linux` 重新生成。
- **runner 那份锁没跟上 extra**：`docker/Dockerfile.plugin-runner:12` 仍在用 sed 剥
  `uvicorn[standard]` ⇒ runner 容器里没有 uvloop/httptools。它与修好的锁兼容（剥掉后
  uvloop 条目不会被要），但"runner 不跑 uvloop"仍然写在构建命令里而不是锁里。
- **OTel 在 CI 上永久跳过**：`importorskip` 让 `TestOtelTraceparentPropagation` 在没装 SDK
  的环境里不出结果。追踪行为目前只有本地（装了 OTel 的 venv）证据，没有 CI 或镜像内的执行
  记录；把它接到镜像内的成本是要在 CI 里真构建并真跑一次 pytest。
- arq 与 opentelemetry 的归属仍在 Dockerfile，锁与镜像不同源这件事没有消除，只是变得可核对。

