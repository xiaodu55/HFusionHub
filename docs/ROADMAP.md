# Roadmap

> HFusionHub project roadmap — updated quarterly.

## Current Status (2026-07)

- **Core**: Stable — Auth, KB CRUD, document upload/parsing, chat with RAG
- **RAG**: Stable — Vector + BM25 hybrid retrieval with RRF
- **Agent**: Stable — ReAct loop with tool calling, SSE streaming
- **MCP**: 4 tools exposed via JSON-RPC 2.0
- **Memory**: Persistent entity facts, summaries, user preferences (V8)
- **Notifications**: System notice table + read tracking (V9)
- **Production**: Docker Compose prod, Helm chart, Grafana dashboard
- **Tests**: Python 655+ ✅ | Java 39 ✅ | Frontend 12 ✅
- **Frontend**: P0-P4 completed — dashboard cleanup, RAG trend chart, notification stub

## Phase 0 — Startup Stability ✅

- [x] Fix README broken links + API docs URL
- [x] Create 17 project docs (architecture, API, DB, environment, etc.)
- [x] Production Docker: shared volumes, callback URLs, healthcheck fixes
- [x] Java datasource/Redis configurable via env vars

## Phase 1 — Core Experience & Visibility ✅

- [x] SSE streaming — WebClient Flux with line-buffered parsing
- [x] Java tests — 39 cases covering AiClient, Memory, Conversation
- [x] Frontend shared components — EmptyState, LoadingSkeleton, ErrorState
- [x] Dashboard cleanup — removed fake trends and static progress
- [x] Feature flags — documented in FEATURE_FLAGS.md

## Phase 2 — Platform Deepening ✅

- [x] MCP integration — JSON-RPC 2.0, 4 tools, internal token auth
- [x] Persistent memory — V8, entity/summary/preference types
- [x] Production deployment — Compose, Helm, Dockerfiles, Nginx
- [x] Prometheus metrics — counters + latency histograms
- [x] Notifications — V9, system_notice table, unread count API

## Phase 3 — Differentiation ✅

- [x] Architecture whitepaper — Java-Python CQRS comparison
- [x] Community — Issue/PR templates, Jupyter notebook, LICENSE
- [x] System diagnostics — `/system/ai-health` preflight endpoint
- [x] RAG trend UI — fixed-height chart, scrollable detail panel

## Phase 4 — Next Priorities (Aug–Sep 2026)

- [ ] **Java tests** — 39→60+ cases covering Document, Vectorization, Auth boundaries
- [ ] **Frontend tests** — 12→30+ covering chat SSE, document upload, login flows
- [ ] **Dynamic feature flags** — DB-driven `feature_flag` table, per-user/KB scoping
- [ ] **Theme system** — light/dark/system tri-state, server-side preference sync
- [ ] **Notification bell** — Frontend unread badge, popup list, admin publish UI
- [ ] **E2E tests** — Playwright or Cypress for critical user journeys
