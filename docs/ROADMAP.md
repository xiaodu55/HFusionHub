# Roadmap

> HFusionHub project roadmap — updated quarterly.

## Current Status (2026-07)

- **Core**: Stable — Auth, KB CRUD, document upload/parsing, chat with RAG
- **RAG**: Stable — Vector + BM25 hybrid retrieval with RRF
- **Agent**: Stable — ReAct loop with tool calling, streaming
- **Tests**: Python 655+ ✅ | Java 40 ✅ | Frontend 12 ✅ (Java/frontend coverage still needs expansion)
- **Advanced features**: P6-P10 implemented, gated behind feature flags

## Phase 0 — Startup Stability ✅

- [x] Fix README broken links
- [x] Create missing docs (java-backend.md, python-ai.md, database.md, api.md)
- [x] Create ENVIRONMENT.md with all required variables
- [x] Fix API docs URL (→ /api/doc.html)
- [x] Create CONTRIBUTING.md
- [x] Document Flyway migration rules

## Phase 1 — Core Experience & Visibility (Jul–Aug 2026)

- [x] **SSE streaming convergence** — Replace hand-rolled HttpURLConnection with unified WebClient Flux
- [ ] **Java test expansion** — 40→60+ test cases, 30%+ core path coverage
- [ ] **Documentation hardening** — startup guides are in place; issue templates and deployment notes still need polish
- [ ] **Feature flag visibility** — FEATURE_FLAGS.md, admin UI for flag status
- [ ] **Frontend UX polish** — Empty states, skeletons, error retry, streaming feedback

## Phase 2 — Platform Deepening (Sep–Nov 2026)

- [ ] **MCP integration** — Expose tools via Model Context Protocol
- [ ] **Persistent memory** — Entity memory, summary compression, cross-session retrieval
- [ ] **RAG evaluation dashboard** — Dataset import, metric trends, RAGAS integration
- [ ] **Production deployment** — Helm chart, Prometheus metrics, Grafana dashboards

## Phase 3 — Differentiation (Dec 2026–Jan 2027)

- [ ] **Architecture whitepaper** — Java-Python hybrid CQRS pattern, benchmarks
- [ ] **Community infrastructure** — Issue/PR templates, sample datasets, notebooks
- [ ] **Low-code tool definitions** — UI-driven custom tool registration

## Feature Stability Matrix

| Feature | Phase | Status | How to Enable |
|---------|-------|--------|---------------|
| User auth (JWT) | P1 | ✅ Stable | Always on |
| Knowledge base CRUD | P1 | ✅ Stable | Always on |
| Document upload + parse | P1 | ✅ Stable | Always on |
| ReAct Agent chat | P2 | ✅ Stable | Always on |
| SSE streaming | P2 | ✅ Stable | Always on |
| Vector + BM25 hybrid | P5 | ✅ Stable | `RAG_HYBRID_ENABLED=true` (default) |
| RAG observability | P5 | ✅ Stable | Always on |
| Scoped GraphRAG | P7 | 🧪 Beta | `RAG_GRAPH_ENABLED=true` |
| Reranker (2nd-stage) | P6 | 🧪 Beta | `RAG_RERANKER_MODE=lexical` or `cross_encoder` |
| Multimodal / OCR | P8 | 🔬 Experimental | `RAG_MULTIMODAL_ENABLED=true` + Tesseract |
| Single-agent workflow | P9 | 🧪 Beta | `RAG_AGENT_WORKFLOW_ENABLED=true` |
| Multi-agent collaboration | P10 | 🔬 Experimental | `RAG_MULTI_AGENT_ENABLED=true` |

## Legend

- ✅ Stable — Production-ready, tested
- 🧪 Beta — Feature-complete, needs more validation
- 🔬 Experimental — Implemented but not fully validated
- 🚧 In Progress — Under active development
- 📋 Planned — On the roadmap
