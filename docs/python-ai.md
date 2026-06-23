# Python AI 服务开发指南

> FastAPI + Milvus (Standalone 默认 / Lite 可选) + DeepSeek API + ReAct Agent + Multi-Channel RAG

## Architecture

The Python AI service owns the **read/intelligence path** — document parsing, chunking, embedding, vector search, RAG retrieval, agent reasoning, and LLM interaction.

```
app/
├── api/              # FastAPI route modules (chat, knowledge, health)
├── core/
│   ├── agent/        # Agent system (ReAct, multi-agent, workflow runtime)
│   ├── chunker/      # Semantic text chunking + quality assessment
│   ├── embedding/    # Embedding services (Ollama, DeepSeek placeholder, test fallback)
│   ├── llm/          # LLM interfaces (DeepSeek, Ollama, mock)
│   ├── parser/       # Document parsers (PDF, DOCX, Markdown, TXT)
│   ├── rag/          # RAG engine (~23 modules)
│   ├── tools/        # Tool system (search, calculator, time)
│   ├── vectorstore/  # Milvus (Standalone 默认 / Lite 可选) + BM25 keyword index
│   └── exceptions.py
├── models/           # Pydantic models
└── utils/            # Configuration, validators
```

> Agent V1 契约（只读研究型 Agent 的能力边界与输入/输出 JSON 契约）见 [agent-v1-scope.md](agent-v1-scope.md)。

## RAG Pipeline (in order)

1. Intent Classification → 2. Query Rewriting → 3. Query Routing → 4. Multi-Channel Retrieval (Vector + BM25 + GraphRAG) → 5. RRF Fusion → 6. Optional Reranking → 7. Postprocessing → 8. Context Compression → 9. ReAct Agent Loop → 10. Self-Reflection → 11. Source Citation

## Feature Flags

All advanced features are gated via environment variables (see `.env.example`):

| Flag | Default | Description |
|------|---------|-------------|
| `RAG_HYBRID_ENABLED` | `true` | Vector + BM25 hybrid retrieval with RRF |
| `RAG_GRAPH_ENABLED` | `false` | Scoped GraphRAG channel (P7) |
| `RAG_RERANKER_MODE` | `disabled` | Second-stage reranking (P6) |
| `RAG_MULTIMODAL_ENABLED` | `false` | OCR/image evidence (P8) |
| `RAG_AGENT_WORKFLOW_ENABLED` | `true` | Bounded single-agent workflow (P9) — 当前 `.env` 已启用 |
| `RAG_MULTI_AGENT_ENABLED` | `false` | Multi-agent collaboration (P10) |

## Setup

```bash
cd python-ai

# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Optional: install test deps
pip install -r requirements-dev.txt
```

## Running

```bash
# From python-ai/ directory with venv activated
python -m app.main

# Or with explicit PYTHONPATH
PYTHONPATH=. python -m app.main
```

Health check: `curl http://localhost:9000/health` → `{"status":"healthy"}`

## Running Tests

```bash
pytest -q tests                    # All tests (1247 functions)
pytest -q tests/test_retriever.py  # Specific module
```

## Key Design Patterns

| Pattern | Where | Purpose |
|---------|-------|---------|
| Strategy | Intent classifier, self-reflector, query router | Swappable LLM/Rule/Hybrid implementations |
| Factory | QueryRouterFactory, IntentClassifierFactory | Configuration-driven creation |
| Singleton | Retriever, config, trace store, graph store | Global instances |
| Provider fallback | LLM (DeepSeek → Ollama → optional mock) | Real provider first; mock only with `LLM_ALLOW_MOCK=true` |
| Embedding strategy | Ollama → fail closed; random only with `EMBEDDING_ALLOW_FALLBACK=true` | Avoid silent fake vectors in production |

## Provider Notes

- `DEEPSEEK_API_KEY` is used for chat LLM calls.
- DeepSeek does not currently provide the embedding API expected by this project; the DeepSeek embedding client raises an error unless test fallback is explicitly enabled.
- For document indexing outside tests, run a real embedding provider such as Ollama and configure `OLLAMA_BASE_URL` plus `OLLAMA_EMBEDDING_MODEL` (note: the `.env.example` variable is `OLLAMA_EMBEDDING_MODEL`, **not** the deprecated `OLLAMA_MODEL`).
- `LLM_ALLOW_MOCK=true` and `EMBEDDING_ALLOW_FALLBACK=true` are development/test switches. Keep both disabled in production.

## SSE Output Format

Python AI returns `text/event-stream` for streaming chat:
```
data: {"content": "token text..."}
data: {"sources": [...]}
data: [DONE]
```

Java backend reads this stream and forwards chunks to the frontend via `SseEmitter`.
