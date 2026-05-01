# HFusionHub 架构白皮书

> Why a Java + Python hybrid architecture for RAG/Agent platforms — and when you should use one.

## Executive Summary

Most production RAG systems are built entirely in Python. This works well for prototypes but creates friction at scale: Python's GIL limits throughput, dynamic typing makes authorization bugs hard to catch, and the ecosystem lacks the battle-tested transaction/connection-pooling infrastructure that Java developers take for granted.

**HFusionHub takes a different approach**: Java owns the write path (ACID transactions, per-user authorization, durable job recovery), while Python owns the read/intelligence path (embeddings, vector search, agent reasoning, LLM interaction). The two communicate via HTTP + SSE + HMAC-signed callbacks.

The result is a system where:
- Every database write goes through compile-time type-checked service layers
- User authorization is enforced at the Java boundary before any AI work begins
- Python can be restarted, crashed, or replaced without data loss
- The LLM ecosystem (LangChain, LlamaIndex, DSPy) remains fully available in Python

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

## Architecture Boundaries

```
┌──────────────────────────────────────────────────────┐
│                    FRONTEND (Vue 3)                   │
│               Port 3000 (dev) / 80 (prod)            │
└────────────────────────┬─────────────────────────────┘
                         │ HTTP/SSE
┌────────────────────────▼─────────────────────────────┐
│                 JAVA BACKEND (:8080)                  │
│  ┌─────────────────────────────────────────────────┐ │
│  │ WRITE PATH                                       │ │
│  │ • Auth (Sa-Token JWT)                           │ │
│  │ • KB CRUD + permission (MyBatis Plus)           │ │
│  │ • Document upload → parse trigger               │ │
│  │ • Conversation/message persistence              │ │
│  │ • Idempotent index jobs (versioned)             │ │
│  │ • Durable deletion (outbox pattern)             │ │
│  │ • Scheduled recovery (index, orphan, recycle)   │ │
│  └─────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────┐ │
│  │ PROXY LAYER                                      │ │
│  │ • AiClient (HTTP → Python)                      │ │
│  │ • SSE forwarding (WebClient Flux → SseEmitter)  │ │
│  │ • HMAC callback verification                    │ │
│  └─────────────────────────────────────────────────┘ │
└────────────────────────┬─────────────────────────────┘
                         │ HTTP + X-Internal-Token
                         │ HMAC callbacks (reverse)
┌────────────────────────▼─────────────────────────────┐
│               PYTHON AI SERVICE (:9000)               │
│  ┌─────────────────────────────────────────────────┐ │
│  │ READ / INTELLIGENCE PATH                         │ │
│  │ • Document parsing (PyMuPDF, python-docx, Tika) │ │
│  │ • Semantic chunking (500/50)                    │ │
│  │ • Embedding (Ollama; test fallback only)        │ │
│  │ • Milvus Standalone vector store (COSINE, IVF_FLAT) │ │
│  │ • Multi-channel RAG: Vector + BM25 + GraphRAG   │ │
│  │ • ReAct Agent loop (max 5 steps)                │ │
│  │ • Intent classification + query decomposition   │ │
│  │ • Self-reflection + source citation             │ │
│  │ • MCP protocol server (JSON-RPC 2.0)            │ │
│  │ • Prometheus metrics export                     │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Idempotent Document Indexing

Each `document_index_job` has an `index_version`. When a new indexing request arrives:
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

## References

- [ARCHITECTURE.md](ARCHITECTURE.md) — detailed architecture diagrams
- [database.md](database.md) — database schema and migration rules
- [ENVIRONMENT.md](ENVIRONMENT.md#feature-flags-python-ai) — P5-P10 feature documentation
- [ROADMAP.md](ROADMAP.md) — project roadmap

---

*HFusionHub — Built with Java's reliability and Python's AI ecosystem.*
