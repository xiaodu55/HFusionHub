# Roadmap

> HFusionHub project roadmap — updated quarterly.

## Current Status (2026-08)

- **Core**: Stable — Auth, KB CRUD, document upload/parsing, chat with RAG
- **RAG**: Stable — Vector + BM25 hybrid retrieval with RRF; Milvus Standalone + external etcd (cluster 模式), Attu 网页控制台查看向量数据
- **Agent**: Stable — ReAct loop with tool calling, SSE streaming
- **MCP**: 7 tools exposed via JSON-RPC 2.0
- **Memory**: Persistent entity facts, summaries, user preferences (V8)
- **Notifications**: System notice table + read tracking (V9)
- **Production**: Docker Compose prod (MySQL/Redis/MinIO/Milvus/etcd/Attu/Java/Python/Plugin Runner), Helm chart, GHCR 镜像发布流水线（`v*` tag 自动构建推送）
- **Release**: 版本 1.0.0；`scripts/setup.ps1/.sh` 一键启动 + `init-env` 自动生成随机密钥；演示数据一键导入；Setup 引导清单
- **Tests**: Python 1220+ ✅ | Java 423 ✅ | Frontend 33 ✅
- **Security**: SECURITY.md / CODE_OF_CONDUCT / NOTICE / dependabot / gitleaks / ruff+pip-audit CI 门禁
- **Frontend**: P0-P4 completed — dashboard cleanup, RAG trend chart, notification stub, SetupChecklist, 能力开关设置页

## Phase 0 — Startup Stability ✅

- [x] Fix README broken links + API docs URL
- [x] Create 17 project docs (architecture, API, DB, environment, etc.)
- [x] Production Docker: shared volumes, callback URLs, healthcheck fixes
- [x] Java datasource/Redis configurable via env vars

## Phase 1 — Core Experience & Visibility ✅

- [x] SSE streaming — WebClient Flux with line-buffered parsing
- [x] Java tests — 397 cases covering AiClient, Memory, Conversation, Document, Vectorization, and Auth boundaries
- [x] Frontend tests — 32 cases covering shared states, chat SSE parsing, document upload, and login flows
- [x] Dashboard cleanup — removed fake trends and static progress
- [x] Feature flags — documented in ENVIRONMENT.md

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

- [x] **Java tests** — 39→79 cases covering Document, Vectorization, and Auth boundaries
- [x] **Frontend tests** — 12→32 covering chat SSE, document upload, and login flows
- [x] **Notification bell** — Frontend unread badge + popup list（真实 AgentAlertEvent 数据）；Admin 公告发布页（公告管理）
- [x] **实验特性三档治理** — 能力开关页新增"稳定 / 实验 / 冻结"三档标注；GraphRAG / 多模态 OCR / Multi-Agent / cross_encoder 重排标记为冻结
- [x] **表格/网页知识摄入** — CSV/XLSX 解析器（纯标准库）+ 网页 URL 抓取（SSRF 防护）纳入文档管线
- [x] **应用发布与开放 API** — app 模型 + 发布 + API Key（哈希存储）+ `/openapi/chat`（限流 + 按 Key 计费）
- [x] **联网搜索** — web_search 支持 DuckDuckGo/Tavily/Serper，`agent.web_search.enabled` flag 门控 + 策略审批
- [x] **MCP Client 管理** — 运行时注册/重连/移除外部 MCP 服务器，持久化配置
- [x] **知识库共享** — kb_share 只读协作，共享用户可创建对话
- [x] **操作审计** — audit_log 表记录应用/API Key/共享/公告等敏感操作
- [x] **在线答案评测** — `/api/rag/evaluate/answer-judge` LLM-as-judge 打分（无标准答案模式）
- [ ] **Dynamic feature flags** — DB-driven `feature_flag` table, per-user/KB scoping（表已建，规则层完善中）
- [ ] **Theme system** — light/dark/system tri-state, server-side preference sync
- [ ] **E2E tests** — Playwright or Cypress for critical user journeys
- [ ] **SSO/OIDC** — 需要外部 IdP 与 sa-token OAuth2 集成，暂缓（会话体系已具备扩展点）
