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
- [ ] **卷可写性** — 应用容器以钉死的 uid 10001 运行、helm 侧同号 fsGroup（见「10. 卷属主与运行身份」）；升级到钉死 uid 前建过的卷需一次性 chown

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

### 10.2 实测（有 docker / 有集群时补一次）

本批的核验只到渲染层（`helm template` 22 个对象、java 与 python 的 podSecurityContext
三项齐备、0 个 `<no value>`）；两个应用镜像本身也未构建（写这一节时本机没有可用的
docker 引擎），所以"钉号 + 建目录"这套命令第一次真实构建即是它的验收。"真的能写"
要在真实环境各跑一次：

```bash
kubectl -n <ns> exec deploy/<rel>-python -- sh -c 'touch /app/uploads/.writable /app/audit-queue/.writable && echo ok'
kubectl -n <ns> exec deploy/<rel>-java   -- sh -c 'mkdir -p /app/uploads/documents && echo ok'
# compose 侧等价物
docker compose exec python-ai sh -c 'touch /data/uploads/.writable && echo ok'
```

### 10.3 已知未收口

- **compose 与 helm 的上传目录语义不等价**：compose 上 python 的 `UPLOAD_DIR=/data/uploads`
  落在 `python-data`，java 写 `uploads-data:/app/uploads`，两个服务的上传分处两卷；
  prod compose 还给 python 挂了 `uploads-data:/app/uploads` 但它从不写这个路径。helm 则
  让两者共用一块 uploads-pvc。是否统一要先回答"java 与 python 是否需要互见对方写的文件"。
- plugin-runner 镜像 uid 未钉 `-u`，1000 只写在 chart 里。
- mysql/etcd/milvus/redis 仍无 pod securityContext（上游镜像以 root 起、入口脚本自 chown）。
