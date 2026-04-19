# HFusionHub Architecture

> English architecture overview of the Java + Python + Vue three-tier AI Agent platform.

## Overview

HFusionHub uses a **CQRS-like three-tier architecture** where Java owns the write path (ACID transactions, per-user authorization) and Python owns the read/intelligence path (embeddings, retrieval, agent reasoning).

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
│  • Document parsing (PDF, DOCX, MD, TXT)               │
│  • Semantic chunking (500 chars, 50 overlap)           │
│  • Embedding generation → Milvus vector store          │
│  • Multi-channel RAG retrieval                        │
│  • ReAct Agent loop (Thought → Action → Observation)  │
│  • LLM interaction (DeepSeek API / Ollama)             │
│  • SSE streaming output                                │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                  Data Layer                             │
├─────────────────────────────────────────────────────────┤
│  • MySQL 8.0  — users, KBs, docs, conversations         │
│  • Redis 7    — cache, sessions, rate limiting          │
│  • Milvus Standalone — 1024-dim FLOAT_VECTOR, COSINE   │
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

## Feature Flag Architecture

Advanced features are gated via environment variables in Python `.env`:

```
RAG_HYBRID_ENABLED=true       # P5 Stable: Vector + BM25 hybrid
RAG_GRAPH_ENABLED=false       # P7 Beta: Scoped GraphRAG
RAG_RERANKER_MODE=disabled    # P6 Beta: Second-stage reranking
RAG_MULTIMODAL_ENABLED=false  # P8 Experimental: OCR/images
RAG_AGENT_WORKFLOW_ENABLED=false  # P9 Beta: Bounded single-agent
RAG_MULTI_AGENT_ENABLED=false # P10 Experimental: Multi-agent
```

See [ENVIRONMENT.md](ENVIRONMENT.md#feature-flags-python-ai) for details on each flag's dependencies and limitations.

## Observability

- **Java**: Actuator health endpoints, scheduler logs
- **Python**: loguru structured logging, RetrievalTrace for per-query RAG diagnostics
- **Frontend**: RAG debug page (`/rag`) with trace viewing
- **Evaluation**: Offline retrieval evaluation against ground-truth case sets
