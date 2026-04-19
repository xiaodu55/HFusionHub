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
| `RAG_GRAPH_ENABLED` | `false` | 🧪 Beta | Scoped graph index built |
| `RAG_RERANKER_MODE` | `disabled` | 🧪 Beta | `pip install -r requirements-reranker.txt` (cross_encoder only) |
| `RAG_MULTIMODAL_ENABLED` | `false` | 🔬 Experimental | Tesseract OCR + `pip install -r requirements-multimodal.txt` |
| `RAG_AGENT_WORKFLOW_ENABLED` | `false` | 🧪 Beta | None (pure Python) |
| `RAG_MULTI_AGENT_ENABLED` | `false` | 🔬 Experimental | Requires P9 enabled + selected KB |

**P5: Hybrid Retrieval (Vector + BM25) — ✅ Stable**

Default: enabled. Combines Milvus vector search with BM25 keyword search via Reciprocal Rank Fusion (RRF). This is the recommended retrieval mode and is fully tested.

**P7: Scoped GraphRAG — 🧪 Beta**

Default: disabled. Builds a per-knowledge-base entity co-occurrence graph. Every node and edge in the graph has source-chunk evidence. When enabled, the graph channel returns only facts whose source chunks remain in the selected knowledge base.

To enable:
1. Set `RAG_GRAPH_ENABLED=true` in `python-ai/.env`
2. Index documents into a knowledge base (graph is built incrementally)
3. Use the RAG debug page to verify graph results appear

Limitations: the graph index is in-memory and rebuilt on restart. Not recommended for KBs with >10,000 documents.

**P6: Second-Stage Reranking — 🧪 Beta**

Default: disabled. Applies a second scoring pass to retrieval candidates before they enter the LLM context.

Modes:
- `disabled` — No reranking (default)
- `lexical` — Deterministic lexical reranking (no extra deps)
- `cross_encoder` — Neural cross-encoder reranking (`pip install -r requirements-reranker.txt`)

Recommendation: keep disabled until an offline benchmark shows improvement over RRF-only retrieval.

**P8: Multimodal Evidence — 🔬 Experimental**

Default: disabled. Extracts text from images in documents via OCR and feeds it into the existing text retrieval pipeline.

Requirements:
1. Install Tesseract OCR on your system
2. `pip install -r requirements-multimodal.txt`
3. Set `RAG_MULTIMODAL_ENABLED=true` and `RAG_MULTIMODAL_OCR_ENABLED=true`

**P9: Bounded Single-Agent Workflow — 🧪 Beta**

Default: disabled. Adds timeout (45s), retry (1 retry, 0.2s delay), and operational run tracking to the ReAct agent. Only whitelisted tools may be invoked.

**P10: Multi-Agent Collaboration — 🔬 Experimental**

Default: disabled. Concurrent expert agents (Retrieval, Analysis, Critic, Synthesis) with a deterministic evidence critic that validates every citation against the knowledge base scope.

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
