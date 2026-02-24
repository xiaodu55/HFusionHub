# Feature Flags

> Advanced RAG features and their configuration.

All advanced features are gated via environment variables in `python-ai/.env`. See `python-ai/.env.example` for the complete list.

## Quick Reference

| Flag | Default | Status | Dependencies |
|------|---------|--------|--------------|
| `RAG_HYBRID_ENABLED` | `true` | ✅ Stable | None |
| `RAG_GRAPH_ENABLED` | `false` | 🧪 Beta | Scoped graph index built |
| `RAG_RERANKER_MODE` | `disabled` | 🧪 Beta | `pip install -r requirements-reranker.txt` (cross_encoder only) |
| `RAG_MULTIMODAL_ENABLED` | `false` | 🔬 Experimental | Tesseract OCR + `pip install -r requirements-multimodal.txt` |
| `RAG_AGENT_WORKFLOW_ENABLED` | `false` | 🧪 Beta | None (pure Python) |
| `RAG_MULTI_AGENT_ENABLED` | `false` | 🔬 Experimental | Requires P9 enabled + selected KB |

## Detailed Status

### P5: Hybrid Retrieval (Vector + BM25) ✅ Stable

**Default: enabled.** Combines Milvus vector search with BM25 keyword search via Reciprocal Rank Fusion (RRF). This is the recommended retrieval mode and is fully tested.

### P7: Scoped GraphRAG 🧪 Beta

**Default: disabled.** Builds a per-knowledge-base entity co-occurrence graph. Every node and edge in the graph has source-chunk evidence. When enabled, the graph channel returns only facts whose source chunks remain in the selected knowledge base.

To enable:
1. Set `RAG_GRAPH_ENABLED=true` in `python-ai/.env`
2. Index documents into a knowledge base (graph is built incrementally)
3. Use the RAG debug page to verify graph results appear

**Limitations**: Graph index is in-memory and rebuilt on restart. Not recommended for KBs with >10,000 documents.

### P6: Second-Stage Reranking 🧪 Beta

**Default: disabled.** Applies a second scoring pass to retrieval candidates before they enter the LLM context.

Modes:
- `disabled` — No reranking (default)
- `lexical` — Deterministic lexical reranking (no extra deps)
- `cross_encoder` — Neural cross-encoder reranking (`pip install -r requirements-reranker.txt`)

**Recommendation**: Keep disabled until an offline benchmark shows improvement over RRF-only retrieval.

### P8: Multimodal Evidence 🔬 Experimental

**Default: disabled.** Extracts text from images in documents via OCR and feeds it into the existing text retrieval pipeline.

Requirements:
1. Install Tesseract OCR on your system
2. `pip install -r requirements-multimodal.txt`
3. Set `RAG_MULTIMODAL_ENABLED=true` and `RAG_MULTIMODAL_OCR_ENABLED=true`

### P9: Bounded Single-Agent Workflow 🧪 Beta

**Default: disabled.** Adds timeout (45s), retry (1 retry, 0.2s delay), and operational run tracking to the ReAct agent. Only whitelisted tools may be invoked.

### P10: Multi-Agent Collaboration 🔬 Experimental

**Default: disabled.** Concurrent expert agents (Retrieval, Analysis, Critic, Synthesis) with a deterministic evidence critic that validates every citation against the knowledge base scope.
