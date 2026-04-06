# Changelog

All notable changes to HFusionHub are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### 验收记录（发布门禁复验）
- **Docker Compose config**：`docker/docker-compose.yml`、`deploy/docker-compose.prod.yml`、`deploy/docker-compose.monitoring.yml` 三个 `config -q` 全部通过
- **Frontend 镜像构建**：`docker build --target build -f deploy/Dockerfile.frontend .` 通过；CI `docker-build` job 的 frontend 改用仓库根 context（`context: .`），Java（`java-backend`）、Python（`python-ai`）context 不变且复验通过
- **代码回归**：Java `mvn test` 397 通过 0 失败；Python `pytest -q` 1219 通过 2 跳过（`tests/test_plugin_container.py` 40 通过）；Frontend `vitest` 32 通过 + `vue-tsc && vite build` 成功
- **Staging 演练**：`scripts/staging-rehearsal.ps1 -NoDind` 退出码 3——mysql8/redis7/milvus/java-backend/plugin-runner/python-ai/frontend 全部 healthy；java/python/frontend 端点 200
- **已知预期**：`-NoDind`（无隔离 Docker Engine）下 runner `/health` 返回 503 属预期（fail-closed）；真实隔离 Docker Engine / Kubernetes 环境留到 staging 机器验证

### Added
- **MCP Protocol**: JSON-RPC 2.0 endpoint at `/mcp` with 4 tools (search, calculate, time, web_search)
- **Persistent Memory**: `memory_entry` table (V8), entity facts, summaries, user preferences
- **System Diagnostics**: `/system/ai-health` preflight endpoint
- **Notifications**: `system_notice` + `notice_recipient` tables (V9), unread count, mark-read API
- **Prometheus Metrics**: `/metrics` endpoint with request counts, latency histograms
- **Jupyter Notebook**: `notebooks/rag_evaluation.ipynb` for RAG evaluation
- **Production Docker**: `deploy/docker-compose.prod.yml`, Dockerfiles, Helm chart
- **Frontend shared components**: `EmptyState`, `LoadingSkeleton`, `ErrorState`
- **Java test coverage**: Expanded from 39 to 79 cases across document ownership and lifecycle, vectorization callbacks and durable job state, and authentication boundaries
- **Frontend test coverage**: Expanded from 12 to 32 cases across chat SSE parsing, document upload requests, and login state flows
- **PR Template**: `.github/PULL_REQUEST_TEMPLATE.md`
- **LICENSE**: Apache-2.0
- Comprehensive project documentation (17 files)

### Changed
- **SSE streaming**: Unified to `WebClient`-based `AiClient.streamChat()` with line-buffered parsing
- Frontend chat streaming now uses a tested incremental SSE parser that preserves split frames and flushes a final line without a trailing newline
- `AiClient.chatStream()` deprecated
- Dashboard: removed fake trend percentages, timeline, and static progress values
- RAG page: fixed-height trend chart, scrollable detail panel with `line-clamp-3`
- Admin flags page renamed to "AI 能力配置说明"
- Feature flags: `LLM_ALLOW_MOCK` defaults to `false` (production-safe)
- Java `application.yml`: datasource URL and Redis host configurable via env vars

### Fixed
- Python chunk detail API: correct `get_document_chunks()` return structure parsing
- Streaming evaluation: buffered chunks into `final_answer` for accurate RAG quality metrics
- Document content update: auto-marked `PENDING` to trigger re-index
- Frontend re-parse: added `processingDocs` tracking for completed documents
- Production Docker: shared upload volume, callback URL, healthcheck commands
- Multiple README broken links and API doc path errors
- MCP security: internal token required for `tools/call`, KB-ID header for search

## [0.1.0] — Initial Release

### Core Platform
- Java Spring Boot 3.2.5 backend with MyBatis Plus, Sa-Token JWT auth
- Python FastAPI AI service with DeepSeek API integration
- Vue 3 + TypeScript + Vite 8 frontend with Radix Vue + Tailwind CSS
- MySQL 8.0 + Redis 7 via Docker Compose
- Flyway database migrations (V1–V8)

### Features
- User authentication (JWT via Sa-Token)
- Knowledge base CRUD with per-user permission management
- Document upload (PDF, DOCX, TXT, Markdown) with Apache Tika parsing
- Semantic text chunking (500 chars, 50 overlap)
- Vector embedding + Milvus Lite storage (1024-dim FLOAT_VECTOR, COSINE)
- ReAct Agent with tool calling (search, calculator, time)
- Multi-channel RAG: Vector (Milvus) + BM25 keyword + Reciprocal Rank Fusion
- Intent classification, query decomposition, context compression, self-reflection
- SSE chat streaming with source citation
- Stream cancellation with idempotency (request_id)
- RAG observability dashboard with debug search and trace viewing
- Offline retrieval evaluation against ground-truth cases

### Advanced (Feature-Flagged)
- P6: Second-stage reranking (cross-encoder or lexical)
- P7: Scoped GraphRAG with entity co-occurrence
- P8: Multimodal evidence (OCR, image enrichment)
- P9: Bounded single-agent workflow with timeout/retry
- P10: Evidence-reviewed multi-agent collaboration with deterministic critic

### Engineering
- HMAC-signed callbacks (Python → Java document processing)
- Durable outbox pattern (deletion_task table)
- Idempotent indexing (index_version-based duplicate rejection)
- Document index recovery scheduler (30-min stale threshold)
- 655+ Python tests, 40 Java tests, 12 frontend tests, CI pipeline (GitHub Actions, 4 parallel jobs)
