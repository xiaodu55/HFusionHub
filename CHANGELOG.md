# Changelog

All notable changes to HFusionHub are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- `docs/java-backend.md` — Java backend development guide
- `docs/python-ai.md` — Python AI service development guide
- `docs/database.md` — Database design and migration rules
- `docs/api.md` — API documentation and authentication guide
- `docs/ARCHITECTURE.md` — English architecture overview
- `docs/ROADMAP.md` — Project roadmap and feature matrix
- `docs/ENVIRONMENT.md` — Complete environment variables reference
- `docs/startup-guide.md` — English startup and restart guide
- `docs/启动重启1.md` — Chinese startup, restart, and troubleshooting guide
- `CONTRIBUTING.md` — Contribution guidelines

### Changed
- **SSE streaming**: Replaced hand-rolled `HttpURLConnection` in `ConversationServiceImpl` with unified `WebClient`-based `AiClient.streamChat()` returning `Flux<String>`
- `AiClient.chatStream()` is now deprecated; new code should use `streamChat()`
- Updated README: fixed API docs URL to `/api/doc.html`, added startup guide references, feature matrix
- Updated environment, database, Java, Python, architecture, and roadmap docs to match current migrations, provider behavior, and test counts

### Fixed
- Fixed broken documentation links in README (5 missing files now exist)
- Fixed README API docs URL pointing to wrong path

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
