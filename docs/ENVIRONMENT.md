# Environment Variables

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
| `REDIS_PASSWORD` | `your_redis_password` | Reserved placeholder; current compose config does not enable Redis password auth |
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

Current Redis password support is incomplete: `docker/redis.conf` and `application.yml` do not wire password authentication end to end. If production Redis requires `requirepass`, add the matching Spring Redis password configuration before relying on `REDIS_PASSWORD` or `SPRING_DATA_REDIS_PASSWORD`.

## Python AI (`python-ai/.env`)

Copy `python-ai/.env.example` to `python-ai/.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | **Yes** | — | DeepSeek API key for chat LLM calls |
| `DEEPSEEK_BASE_URL` | No | `https://api.deepseek.com` | DeepSeek API endpoint |
| `DEEPSEEK_MODEL` | No | `deepseek-v4-flash` | Model name |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama URL for local LLM fallback and embeddings |
| `OLLAMA_EMBEDDING_MODEL` | No | `qwen3-embedding:8b-fp16` | Ollama embedding model (**use this**, not the deprecated `OLLAMA_MODEL`) |
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
| `RAG_RERANKER_MODE` | `disabled` | 🧪 Beta（cross_encoder 已冻结） | `pip install -r requirements-reranker.txt` (cross_encoder only) |
| `RAG_MULTIMODAL_ENABLED` | `false` | ❄️ Frozen | Tesseract OCR + `pip install -r requirements-multimodal.txt` |
| `RAG_AGENT_WORKFLOW_ENABLED` | `false` | 🧪 Beta | None (pure Python) |
| `RAG_MULTI_AGENT_ENABLED` | `false` | ❄️ Frozen | Requires P9 enabled + selected KB |

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

**P9: Bounded Single-Agent Workflow — 🧪 Beta**

默认关闭。为 ReAct Agent 增加超时（45s）、重试（1 次，0.2s 延迟）与运行追踪。仅白名单工具可被调用。

**P10: Multi-Agent Collaboration — ❄️ 冻结（不再投入）**

默认关闭。并发专家 Agent（检索/分析/校验/综合）+ 确定性证据校验器。

> **治理状态（2026-08）**：已冻结。实验性、增加延迟、critic 仅单库校验，收益不明确。保留为研究项目。

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
