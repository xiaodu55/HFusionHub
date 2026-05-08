# HFusionHub 架构全景

> Java + Python + Vue 三层的 CQRS-like 企业级 AI Agent 平台架构。
> This document merges the former ARCHITECTURE.md overview and WHITEPAPER.md rationale into a single source of truth.

## Overview

HFusionHub uses a **CQRS-like three-tier architecture** where Java owns the write path (ACID transactions, per-user authorization) and Python owns the read/intelligence path (embeddings, retrieval, agent reasoning).

### Why a Java + Python Hybrid?

Most production RAG systems are built entirely in Python. This works well for prototypes but creates friction at scale: Python's GIL limits throughput, dynamic typing makes authorization bugs hard to catch, and the ecosystem lacks the battle-tested transaction/connection-pooling infrastructure that Java developers take for granted.

**HFusionHub takes a different approach**: Java owns the write path (ACID transactions, per-user authorization, durable job recovery), while Python owns the read/intelligence path (embeddings, vector search, agent reasoning, LLM interaction). The two communicate via HTTP + SSE + HMAC-signed callbacks.

The result is a system where:
- Every database write goes through compile-time type-checked service layers
- User authorization is enforced at the Java boundary before any AI work begins
- Python can be restarted, crashed, or replaced without data loss
- The LLM ecosystem (LangChain, LlamaIndex, DSPy) remains fully available in Python

```
┌─────────────────────────────────────────────────────────┐
│                 Frontend (Vue 3 :3000)                   │
│          Radix Vue + Tailwind CSS + Pinia               │
│          Axios with Sa-Token header injection           │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP/SSE (Vite proxies /api → :8080)
┌─────────────────────▼───────────────────────────────────┐
│              Java Backend (Spring Boot 3.2 :8080)       │
│          /api context-path, Sa-Token JWT auth           │
├─────────────────────────────────────────────────────────┤
│  Write Path (ACID):                                     │
│  • User auth & session management                      │
│  • Knowledge base CRUD + permission checks             │
│  • Document upload → parse trigger → Python callback   │
│  • Conversation & message persistence (MySQL)          │
│  • Durable job recovery (index, deletion, orphan)      │
│  • Durable deletion outbox (deletion_task)             │
│                                                         │
│  Proxy Layer:                                           │
│  • AiClient → HTTP → Python AI (:9000)                │
│  • SseEmitter → SSE forwarding → Frontend              │
│  • HMAC-signed callbacks from Python                   │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP + X-Internal-Token
                      │ HMAC callbacks (reverse)
┌─────────────────────▼───────────────────────────────────┐
│           Python AI Service (FastAPI :9000)             │
├─────────────────────────────────────────────────────────┤
│  Read/Intelligence Path:                                │
│  • Document parsing (PyMuPDF, python-docx, Tika)       │
│  • Semantic chunking (500 chars, 50 overlap)           │
│  • Embedding generation (Ollama; test fallback only)   │
│  • Milvus Standalone vector store (1024-dim COSINE)    │
│  • Multi-channel RAG: Vector + BM25 + GraphRAG         │
│  • ReAct Agent loop (Thought → Action → Observation)   │
│  • LLM interaction (DeepSeek API / Ollama)             │
│  • Intent classification + query decomposition         │
│  • Self-reflection + source citation                   │
│  • MCP protocol server (JSON-RPC 2.0)                  │
│  • SSE streaming output + Prometheus metrics           │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                  Data Layer                             │
├─────────────────────────────────────────────────────────┤
│  • MySQL 8.0  — users, KBs, docs, conversations         │
│  • Redis 7    — cache, sessions, rate limiting          │
│  • Milvus Standalone — 1024-dim FLOAT_VECTOR, COSINE   │
│  • MinIO      — file / artifact object storage         │
│  • Local FS   — uploaded documents, graph index         │
└─────────────────────────────────────────────────────────┘
```

## Data Flow: Chat Message (SSE)

```
1. Frontend POST /api/conversation/message/stream (SSE)
2. Java ConversationController → ConversationServiceImpl.sendMessageStream()
3. Java saves user message (MySQL, idempotent via request_id)
4. Java AiClient.streamChat() → WebClient POST to Python :9000/api/chat/stream
5. Python ReactAgent processes:
   a. Intent classification → query rewriting
   b. Multi-channel retrieval (Vector + BM25 + optional GraphRAG)
   c. ReAct loop: Thought → Action → Observation (max 5 steps)
   d. Context compression + self-reflection
   e. SSE stream: data: {"content":"..."}, data: {"sources":[...]}, data: [DONE]
6. Java reads Flux<String> SSE lines, forwards to frontend via SseEmitter
7. Java saves assistant message (MySQL, after [DONE] or on error)
```

## Data Flow: Document Indexing

```
1. Frontend uploads file → Java DocumentController
2. Java saves Document entity (MySQL, status=PENDING)
3. Java creates DocumentIndexJob (MySQL, versioned)
4. Java calls Python /api/vectorize via AiClient
5. Python parses → chunks → embeds → stores in Milvus (cluster 模式)
6. Python HMAC-signs callback → Java /api/vectorize/*/callback
7. Java updates Document status → COMPLETED (or FAILED)
8. Recovery: DocumentIndexRecoveryScheduler rescues stale jobs (30-min threshold)
```

## Key Design Decisions

### 1. Idempotent Document Indexing

Each `document_index_job` has an `index_version` (UUID). When a new indexing request arrives:
1. Java increments the version
2. Python receives the version in the API call
3. Python's callback includes the version
4. Java only accepts callbacks where `callback.version == job.index_version`

This prevents: stale callbacks from crashed workers, duplicate processing, and "phantom indexing" where a document appears processed but isn't.

### 2. HMAC-Signed Callbacks

Python → Java callbacks are HMAC-signed with a shared `CALLBACK_SECRET`. This prevents unauthorized callbacks from bypassing Java's authorization layer.

### 3. Durable Deletion Outbox

Documents are soft-deleted. A `deletion_task` outbox table tracks async cleanup with retry limits. A scheduler (`DeletionTaskScheduler`) processes pending deletions. This avoids: orphaned Milvus vectors, partial deletes under crash, and the need for distributed transactions.

### 4. Feature Flag Architecture

P6-P10 features are gated by environment variables, not code paths. This means:
- Features can be enabled/disabled without rebuild
- Each flag has documented dependencies and limitations
- Experimental features (multi-agent, multimodal) default to OFF
- Stable features (hybrid retrieval) default to ON

## Security Boundaries

| Boundary | Mechanism |
|----------|-----------|
| User → Java | Sa-Token JWT (86400s timeout, 1800s active) |
| Java → Python | `X-Internal-Token` header (constant-time comparison) |
| Python → Java callback | HMAC-SHA256 with `CALLBACK_SECRET` |
| KB ownership | Checked at Java service layer (user_id match) |
| Frontend → Java | Axios interceptor injects `satoken` header |

## Key Design Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| CQRS-like | Java ↔ Python | Java: ACID writes. Python: vector search + LLM. |
| Strategy | Intent classifier, reflector, router | Swappable LLM/Rule/Hybrid implementations |
| Idempotent indexing | document_index_job.index_version | Duplicate callbacks rejected |
| Durable outbox | deletion_task table | Async cleanup survives restarts |
| Provider fallback | LLM (DeepSeek → Ollama → optional mock), Embedding (Ollama → fail closed unless test fallback is enabled) | Avoid silent fake vectors in production |
| Circuit breaker | Model router | Multi-model priority with health checks |

## The Problem with Pure Python RAG

| Concern | Pure Python | HFusionHub |
|---------|------------|------------|
| **Authorization** | Decorators on FastAPI routes; easy to miss | Compile-time checked in Java service layer |
| **Transaction safety** | Manual `try/finally` with SQLAlchemy | `@Transactional` — automatic rollback |
| **Connection pooling** | psycopg2 pool or asyncpg | HikariCP — industry standard, 10+ years |
| **Schema migrations** | Alembic (manual ordering) | Flyway (deterministic, versioned) |
| **Type safety** | Pydantic at API boundary only | Java compiler across all layers |
| **Concurrency** | GIL limits CPU-bound work | True multi-threading for I/O-bound tasks |
| **Job recovery** | Celery + Redis, complex retry logic | `@Scheduled` + idempotent versioned jobs |

## Performance Characteristics

| Operation | Typical Latency | Bottleneck |
|-----------|----------------|------------|
| Document upload (small PDF) | 2-5s | Python parsing + embedding |
| Chat (RAG, streaming) | 3-8s TTFT | LLM generation |
| Vector search (10K chunks) | 50-200ms | Milvus I/O |
| BM25 keyword search | 10-50ms | In-memory index |
| GraphRAG traversal | 100-500ms | Entity resolution |
| User auth | <5ms | Redis JWT lookup |

## When to Use This Architecture

**Good fit for:**
- Multi-tenant SaaS with per-user knowledge base isolation
- Systems requiring audit trails and compliance (Java's type safety)
- Teams with Java backend engineers who want to add AI capabilities
- Projects where data integrity matters more than raw ML throughput

**Not a good fit for:**
- Solo ML research projects (pure Python is simpler)
- Systems where the LLM is the entire application (no CRUD)
- Teams without Java expertise

## Comparison with Alternatives

| | HFusionHub | Dify | Ragent | LangChain |
|---|---|---|---|---|
| **Language** | Java + Python | Python + React | Java | Python |
| **RAG** | Multi-channel + GraphRAG | Visual workflow | Enterprise pipelines | Modular chains |
| **Auth** | JWT + per-KB ACL | Workspace-based | RBAC | DIY |
| **Deployment** | Docker / K8s | Docker / Cloud | Docker | Library |
| **Evaluation** | Built-in + RAGAS | Annotation | ragenteval | LangSmith |
| **MCP** | ✅ Native | Community | Built-in | Via adapter |

## Feature Flag Architecture

Advanced features are gated via environment variables in Python `.env`. **Frozen statuses as of 2026-08-19**:

```
RAG_HYBRID_ENABLED=true          # P5 Stable: Vector + BM25 hybrid
RAG_GRAPH_ENABLED=false          # P7 Beta: Scoped GraphRAG
RAG_RERANKER_MODE=disabled       # P6 Beta: Second-stage reranking
RAG_MULTIMODAL_ENABLED=false     # P8 Experimental: OCR/images
RAG_AGENT_WORKFLOW_ENABLED=true  # P9 Beta: Bounded single-agent (当前已启用)
RAG_MULTI_AGENT_ENABLED=false    # P10 Experimental: Multi-agent
```

See [ENVIRONMENT.md](ENVIRONMENT.md#feature-flags-python-ai) for details on each flag's dependencies and limitations.

## Observability

- **Java**: Actuator health endpoints (`/api/actuator/health`), scheduler logs
- **Python**: loguru structured logging, RetrievalTrace for per-query RAG diagnostics, Prometheus metrics
- **Frontend**: RAG debug page (`/rag`) with trace viewing
- **Evaluation**: Offline retrieval evaluation against ground-truth case sets

## References

- [database.md](database.md) — database schema and migration rules
- [ENVIRONMENT.md](ENVIRONMENT.md#feature-flags-python-ai) — P5-P10 feature documentation
- [ROADMAP.md](ROADMAP.md) — project roadmap
- [java-backend.md](java-backend.md) — Java 后端开发指南
- [python-ai.md](python-ai.md) — Python AI 开发指南
