# 环境变量清单

> Required and optional environment variables for HFusionHub services.

## Quick Reference (Windows PowerShell)

```powershell
# Copy-paste this block and replace placeholder values
$env:MYSQL_ROOT_PASSWORD="replace-with-a-strong-root-password"
$env:MYSQL_PASSWORD="replace-with-a-strong-db-password"
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD=$env:MYSQL_PASSWORD
$env:CALLBACK_SECRET="replace-with-a-long-random-callback-secret"
$env:PYTHON_AI_INTERNAL_TOKEN="replace-with-a-long-random-internal-token"
$env:ADMIN_PASSWORD="replace-with-a-strong-admin-password"
$env:AI_SERVICE_URL="http://localhost:9000"
$env:PYTHON_AI_CALLBACK_BASE_URL="http://localhost:8080/api"
$env:DEEPSEEK_API_KEY="replace-with-your-deepseek-api-key"
```

## Docker Compose (`docker/.env`)

Copy `docker/.env.example` to `docker/.env`:

| Variable | Example | Description |
|----------|---------|-------------|
| `MYSQL_ROOT_PASSWORD` | `root123456` | MySQL root password |
| `MYSQL_PASSWORD` | `hfusionhub123` | MySQL app user password |
| `REDIS_PASSWORD` | `your_redis_password` | Redis `requirepass`。dev compose（`docker/docker-compose.yml`）已通过 `--requirepass` 启用；**设置后 Java 必须注入同名 `REDIS_PASSWORD`**，否则启动报 `NOAUTH Authentication required`（见 2026-08-21 修复 cf07937） |
| `ADMIN_PASSWORD` | `changeme` | Bootstrap admin password |
| `MINIO_ROOT_USER` | `minioadmin` | MinIO object storage username |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | MinIO object storage password |
| `PLUGIN_RUNNER_TOKEN` | *(random)* | Plugin sandbox runner auth token (required — compose fails without it) |

### Production (`deploy/.env`)

Copy `deploy/.env.example` to `deploy/.env` for production Docker Compose:

| Variable | Required | Description |
|----------|----------|-------------|
| `MYSQL_ROOT_PASSWORD` | **Yes** | MySQL root password |
| `MYSQL_PASSWORD` | **Yes** | MySQL app user password |
| `PYTHON_AI_INTERNAL_TOKEN` | **Yes** | Java ↔ Python shared secret |
| `CALLBACK_SECRET` | **Yes** | HMAC secret for Python → Java callbacks |
| `ADMIN_PASSWORD` | **Yes** | Bootstrap admin account |
| `PLUGIN_RUNNER_TOKEN` | **Yes** | Plugin sandbox runner auth |
| `DEEPSEEK_API_KEY` | **Yes** | DeepSeek API key for chat LLM |
| `PLUGIN_RUNNER_DOCKER_HOST` | **Yes** | TLS Docker Engine for plugin isolation |
| `PLUGIN_RUNNER_CA_CERT_FILE` | **Yes** | Path to runner TLS CA cert |
| `PLUGIN_RUNNER_CLIENT_CERT_FILE` | **Yes** | Path to runner TLS client cert |
| `PLUGIN_RUNNER_CLIENT_KEY_FILE` | **Yes** | Path to runner TLS client key |

## Java Backend (`java-backend/`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_USERNAME` | No | `hfusionhub` | MySQL username |
| `DB_PASSWORD` | **Yes** | — | MySQL password (must match `MYSQL_PASSWORD`) |
| `SPRING_DATASOURCE_URL` | Container | local MySQL URL | MySQL JDBC URL; required when Java runs in Docker/K8s |
| `SPRING_DATA_REDIS_HOST` | Container | `127.0.0.1` | Redis host; set to `redis7`/service name in containers |
| `SPRING_DATA_REDIS_PORT` | No | `6379` | Redis port |
| `PYTHON_AI_INTERNAL_TOKEN` | **Yes** | — | Shared secret for Java ↔ Python |
| `CALLBACK_SECRET` | **Yes** | — | HMAC secret for Python → Java callbacks |
| `ADMIN_PASSWORD` | **Yes** | — | Bootstrap admin account password |
| `AI_SERVICE_URL` | No | `http://localhost:9000` | Python AI service URL |
| `PYTHON_AI_CALLBACK_BASE_URL` | Container | `http://localhost:8080/api` | Java callback base URL reachable from Python |
| `AI_SERVICE_TIMEOUT` | No | `120000` | Timeout in ms |
| `RAG_INDEX_STALE_AFTER_MINUTES` | No | `30` | Index job recovery threshold |
| `RAG_INDEX_MAX_ATTEMPTS` | No | `3` | Max indexing retries |
| `TRUSTED_PROXY_HEADERS` | No | `false` | Enable X-Forwarded-For (reverse proxy only) |
| `DEMO_ENDPOINTS_ENABLED` | No | `true`（dev）/ `false`（prod compose） | `/demo/*` 演示数据端点总开关（import/clear/import-bid 等）；关闭时返回 403。生产默认关闭——`/demo/clear` 有数据破坏性；生产 compose 与 `deploy/.env.example` 已默认 `false` |

> Redis 密码：dev compose 已在 `docker/docker-compose.yml` 通过 `redis-server ... --requirepass "$REDIS_PASSWORD"` 启用（2026-08-21 起生效）。Java 侧 `application.yml` 读取 `REDIS_PASSWORD`，**两端必须一致**，否则 Java 启动报 NOAUTH。生产若 Redis 关闭 requirepass，将 `REDIS_PASSWORD` 留空即可。

### SSO/OIDC 单点登录（Java Backend，默认关闭）

通用 OIDC 客户端（授权码流程），经 `app.oidc.*` 对接外部 IdP（Keycloak / Google / Azure AD / 企业微信 等）。完整接入步骤见 [docs/OIDC.md](OIDC.md)。

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `OIDC_ENABLED` | 是 | `false` | `true` 时登录页展示 SSO 入口 |
| `OIDC_PROVIDER_NAME` | 否 | `generic` | 存入 `sys_user.oauth_provider` |
| `OIDC_AUTHORIZATION_ENDPOINT` | 是 | — | IdP 授权端点 |
| `OIDC_TOKEN_ENDPOINT` | 是 | — | IdP 令牌端点 |
| `OIDC_USERINFO_ENDPOINT` | 是 | — | IdP 用户信息端点 |
| `OIDC_CLIENT_ID` | 是 | — | 在 IdP 注册的 client id |
| `OIDC_CLIENT_SECRET` | 是 | — | client secret（机密） |
| `OIDC_REDIRECT_URI` | 是 | — | 本应用回调地址（需在 IdP 白名单注册） |
| `OIDC_FRONTEND_REDIRECT_URI` | 否 | — | 登录成功后前端落地地址（携带 `?token=`） |
| `OIDC_SCOPES` | 否 | `openid profile email` | 授权范围 |
| `OIDC_USERNAME_CLAIM` / `OIDC_EMAIL_CLAIM` / `OIDC_NAME_CLAIM` | 否 | `preferred_username` / `email` / `name` | userinfo 声明名映射 |
| `OIDC_AUTO_PROVISION` | 否 | `true` | 首次 SSO 登录自动开户（role=pending） |
| `OIDC_LINK_BY_EMAIL` | 否 | `true` | 允许按已验证邮箱关联既有账号 |

## Python AI (`python-ai/.env`)

Copy `python-ai/.env.example` to `python-ai/.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | **Yes** | — | DeepSeek API key for chat LLM calls |
| `DEEPSEEK_BASE_URL` | No | `https://api.deepseek.com` | DeepSeek API endpoint |
| `DEEPSEEK_MODEL` | No | `deepseek-v4-flash` | Model name (chat only, DeepSeek does not provide embedding API) |
| `LLM_HTTP_TIMEOUT_SECONDS` | No | `120` | 共享 HTTP 客户端单请求上游超时（P3） |
| `LLM_MAX_RETRIES` | No | `3` | 429/5xx/连接错误的额外重试次数（首次调用后的重试上限，P3） |
| `LLM_RETRY_BACKOFF_SECONDS` | No | `0.5` | 指数退避基础秒数（每次翻倍 + jitter，P3） |
| `LLM_RESPONSE_CACHE_TTL_SECONDS` | No | `300` | LLM 响应缓存 TTL（P9）；设为 0 禁用缓存 |
| `MODEL_GATEWAY_STREAM_ENABLED` | No | `true` | 让 agent/chat 的 LLM 调用（含流式）走 ModelGateway：限流/熔断/计费/响应缓存对流式同样生效；设 `false` 走旧 `get_llm()` 链（测试会话强制关闭） |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama URL for local LLM fallback and embeddings |
| `OLLAMA_EMBEDDING_MODEL` | No | `bge-m3:latest` | Ollama embedding model (**use this**, not the deprecated `OLLAMA_MODEL`；当前 `.env` 使用 `bge-m3:latest`） |
| `OPENAI_COMPATIBLE_API_KEY` | No | `` | OpenAI 兼容备用供应商（B2）：加入 FailoverLLM 链，主供应商故障时切换 |
| `OPENAI_COMPATIBLE_BASE_URL` | No | `` | 同上，chat-completions 兼容端点（OpenAI/通义/Kimi 等） |
| `OPENAI_COMPATIBLE_MODEL` | No | `` | 同上，模型名（空则用 DEEPSEEK_MODEL） |
| `WEB_SEARCH_PROVIDER` | No | `duckduckgo` | 联网搜索后端：`duckduckgo`（免 Key）/ `tavily` / `serper` |
| `WEB_SEARCH_API_KEY` | No | `` | Tavily / Serper 的 API Key |
| `WEB_SEARCH_BASE_URL` | No | `` | 搜索 API 地址覆盖（可选） |
| `MCP_SERVERS_CONFIG` | No | `` | MCP 客户端启动配置（JSON 数组）；运行时变更持久化到 `MCP_SERVERS_CONFIG_FILE` |
| `LLM_ALLOW_MOCK` | No | `false` | Enables mock LLM for development/testing only |
| `SERVER_HOST` | No | `0.0.0.0` | FastAPI bind address |
| `SERVER_PORT` | No | `9000` | FastAPI port |
| `CORS_ORIGINS` | No | `http://localhost:5173,...` | Allowed CORS origins |
| `JAVA_BACKEND_URL` | No | `http://localhost:8080` | Callback target |
| `CHUNK_SIZE` | No | `500` | Text chunk size |
| `CHUNK_OVERLAP` | No | `50` | Chunk overlap |
| `EMBEDDING_DIMENSION` | No | `1024` | Vector dimension |
| `EMBEDDING_ALLOW_FALLBACK` | No | `false` | Enables random-vector fallback for development/testing only |

DeepSeek does not provide the embedding API used here. For document indexing outside tests, configure Ollama or another real embedding provider; keep `EMBEDDING_ALLOW_FALLBACK=false` in production.

The frontend dev server runs on `http://localhost:3000`. Normal browser traffic goes through the Vite `/api` proxy to Java, so Python CORS is usually not involved. If a browser client calls Python directly, include `http://localhost:3000` in `CORS_ORIGINS`.

### Feature Flags (Python AI)

All advanced RAG features are gated via environment variables in `python-ai/.env` (or runtime-synced from the Java backend via `/api/feature-flag/all` when `JAVA_BACKEND_URL` is set). See `python-ai/.env.example` for the complete list.

| Flag | Default | Status | Dependencies |
|------|---------|--------|--------------|
| `RAG_HYBRID_ENABLED` | `true` | ✅ Stable | None |
| `RAG_GRAPH_ENABLED` | `false` | ❄️ Frozen | Scoped graph index built |
| `RAG_RERANKER_MODE` | `lexical` | ✅ 稳定（默认启用；`rag.reranker.enabled` 已默认开启，前端「能力开关」页可关） | `lexical` 零依赖；`cross_encoder` 需 `pip install -r requirements-reranker.txt`（模型不可用时自动降级不中断服务） |
| `RAG_MULTIMODAL_ENABLED` | `false` | ❄️ Frozen | Tesseract OCR + `pip install -r requirements-multimodal.txt` |
| `RAG_AGENT_WORKFLOW_ENABLED` | `true` | 🧪 Beta | None (pure Python)；当前 `.env` 已启用 |
| `RAG_MULTI_AGENT_ENABLED` | `false` | 🧪 Beta（V59 起 flag 默认开启） | Requires P9 enabled + selected KB（运行时由 `agent.multi_agent.enabled` flag 控制） |

**P5: Hybrid Retrieval (Vector + BM25) — ✅ Stable**

Default: enabled. Combines Milvus vector search with BM25 keyword search via Reciprocal Rank Fusion (RRF). This is the recommended retrieval mode and is fully tested.

**P7: Scoped GraphRAG — ❄️ 冻结（不再投入）**

默认关闭。构建每知识库的实体共现图，图通道仅返回仍存在于选定知识库中的事实。

> **治理状态（2026-08）**：已冻结。图索引为内存实现、重启重建，文档自述不推荐用于 >10,000 文档的知识库，收益不稳定。代码与测试保留，UI 已标注"冻结"，不再投入新功能。

**P6: Second-Stage Reranking — 🧪 Beta（cross_encoder 模式已冻结）**

默认关闭。对检索候选进行二次打分后进入 LLM 上下文。

Modes:
- `disabled` — 不重排（默认）
- `lexical` — 确定性词法重排（无额外依赖）✅ 建议模式
- `cross_encoder` — 神经交叉编码器重排 ❄️ 已冻结（需 `pip install -r requirements-reranker.txt`，收益未获离线基准证明前不投入）

**P8: Multimodal Evidence — ❄️ 冻结（不再投入）**

默认关闭。通过 OCR 从文档图片提取文本进入文本检索管线。

> **治理状态（2026-08）**：已冻结。依赖系统级 Tesseract、收益低。等 vision-LLM 路线（可选 C5）再重启。

**P9: Bounded Single-Agent Workflow — 🧪 Beta（当前已启用）**

默认开启（当前 `.env` 为 `true`）。为 ReAct Agent 增加超时（45s）、重试（1 次，0.2s 延迟）与运行追踪。仅白名单工具可被调用。

**P10: Multi-Agent Collaboration — 🧪 Beta（默认开启）**

默认开启（Flyway V59 起 `agent.multi_agent.enabled` 默认 TRUE）。并发专家 Agent（检索/分析/校验/综合）+ 确定性证据校验器；输出缓冲至 citations 通过本地范围校验。

> **治理状态（2026-08-24）**：已按用户要求解除冻结（V59）。实验性、增加延迟、critic 仅单库校验；仍可在前端「能力开关」页按需关闭。

## Critical: PYTHON_AI_INTERNAL_TOKEN

This token **must be identical** in both:
1. Java backend terminal (`$env:PYTHON_AI_INTERNAL_TOKEN="..."`)
2. Python AI terminal (`$env:PYTHON_AI_INTERNAL_TOKEN="..."`)

If they differ, all Java → Python requests will fail with 401/403.

## Critical: DB_PASSWORD = MYSQL_PASSWORD

The Java `DB_PASSWORD` must match the `MYSQL_PASSWORD` used when starting Docker. Using Docker:
```powershell
# docker/.env (or inline env)
MYSQL_PASSWORD=mysecurepassword

# Java backend terminal
$env:DB_PASSWORD="mysecurepassword"
```

## Security Notes

- **Never commit** `.env` files or hardcoded secrets to Git
- Use `docker/.env.example` and `python-ai/.env.example` as templates
- For production, use a secrets manager (Vault, AWS Secrets Manager, etc.) or K8s Secrets
