# Changelog

All notable changes to HFusionHub are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### 第八轮优化（2026-08-19）：各菜单一键导入示例数据

#### Added
- **演示数据一键导入升级**：`POST /demo/import` 从仅导入演示知识库扩展为覆盖 6 个菜单——知识库文档（3 篇）、回答方案（客服答疑/文档总结/代码审查 3 个已发布模板，与前端内置示例文案一致）、我的笔记（周会纪要 + RAG 调优笔记 2 篇，`demo/notes/` classpath 资源）、我的记忆（1 条偏好 + 1 条实体事实）、应用发布（1 个绑定演示 KB 的草稿应用）、公告管理（1 条欢迎公告，通知铃铛全员可见）；全部按「用户 + 名称/标题」判重幂等，`DemoImportResultDTO` 新增 `sections` 分项计数
- **MCP 服务示例预填**：添加对话框新增「填入示例」按钮（Notion MCP 官方端点示例），空状态提示更新

#### Fixed
- `notes/Index.vue` 新建笔记 `rows="8"` 字符串传入 number 类型 prop 导致 `vue-tsc` 构建失败（预存问题，`:rows="8"` 修复）

#### Notes
- 模型用量/运行记录/待确认/回答效果等真实运行数据页**不**注入演示数据（与此前移除仪表盘假趋势的决策一致）
- 测试：Java 443 全过（`DemoImportServiceImplTest` 扩展为 3 场景 × 6 分项断言）；前端 build 通过 + Vitest 33/33

### 第七轮优化（2026-08-18）：写笔记闭环 + 全栈验证修复 + 工程化补课

#### Added
- **写笔记闭环（P0–P4 全链路）**：`note` 表（Flyway V55）+ `NoteController` 用户笔记 CRUD + `InternalNoteController`（Python write_note 回调，X-Internal-Token 保护）；Python `write_note_tool` 从占位实现改为真实持久化（回调 Java `/api/internal/notes`）；前端聊天"需要你的确认"审批卡片 + 「我的笔记」页面（列表/查看/下载/删除）；E2E `e2e/write-note.spec.ts`（3 项通过）
- **工程化脚本**：`scripts/smoke-test.ps1`（全功能冒烟，41 项全过）、`scripts/static-checks.py`（租户列完整性 + internal token 键一致性，接入 CI `static-consistency` job）、`scripts/verify-agent-workflow.ps1`（Agent 工作流回归验证）
- **管理端审计视图**：`AuditController`（`GET /admin/audit-logs/operations` + `/cross-tenant`）
- **开放 API 用量打通**：`OpenApiServiceImpl` 成功调用额外落 `model_usage_record`（/cost 页面可见开放 API 用量）
- **模型用量链路接通**：`ConversationServiceImpl`/`AgentTaskServiceImpl` 聊天与 Agent 完成时写 `model_usage_record`（此前 `record()` 无调用方，/cost 永远为空）
- **web_search 工具修复**：嵌套 Topics 展开 + lite HTML 搜索 fallback（Instant Answer 空结果不再返回空）；`agent.web_search.enabled=1`
- **意图分类写操作**：OPERATION 关键词补"保存/写入/整理成笔记/保存到"等 + LLM 分类提示词增强（"把结论整理成笔记保存到知识库"→ operation/tool_execution）

#### Fixed
- **`kb_share` / `app_api_key` 缺 `tenant_id` 列（V56）**：两表被租户拦截器注入 `WHERE tenant_id=?` 导致整表功能 500（知识库共享、开放 API Key 管理从 V52/V53 建表起不可用）——补列 + 回填 + 索引
- **`FeatureFlagInternalController` token 键错误**：`${app.internal-token}`（未定义）→ `${python-ai.internal-token}`；Python 从 0 flags → 8 flags
- **Agent workflow 工具白名单漏 write_note**：`get_agent` 的 `ToolExecutionPolicy`/`SingleAgentWorkflow.allowed_tools` 仅含 3 只读工具导致 write_note 永不可见——approval_write 能力时放行
- **workflow 状态映射缺失**：`waiting_approval` 被映射为 completed，已修复
- **SaTokenConfig**：`/internal/notes/**` 加入登录白名单

#### Docs
- 新增 `docs/PROJECT_ASSESSMENT.md`（全栈评估报告）、`docs/PRODUCTION_CHECKLIST.md`（生产核对清单）、`docs/PLUGIN_RUNNER_TLS.md`（Runner TLS 指引）；重写 `docs/database.md`（V1–V56 全迁移表）；`AGENTS.md`/`CLAUDE.md` 迁移版本更新至 V56 + 新表说明；英文文档标题中文化（api/architecture/database/env/java/python/roadmap/whitepaper/dr_vectors）

#### Notes
- feature flags 现状：`agent.enabled=1`、`agent.write_tools.enabled=1`、`agent.web_search.enabled=1`、`approval.required_for_write=1`（`agent.multi_agent.enabled=0` 保持冻结）；`RAG_AGENT_WORKFLOW_ENABLED=true`
- `DEEPSEEK_API_KEY` 当前为占位符（聊天走 Ollama）；配置真实 key 后自动 DeepSeek 优先（代码逻辑已验证）
- Plugin Runner 在本机仍 unhealthy（Docker daemon TLS 需主机级配置，见 `docs/PLUGIN_RUNNER_TLS.md`）

## [Unreleased]

### 第六轮优化（2026-08-17）：应用化发布 + 知识摄入扩展 + 治理收口

#### Added
- **应用发布（B1/C4）**：`app` + `app_api_key` + `app_call_log` 表（Flyway V52）；应用 CRUD/发布/撤回；API Key SHA-256 哈希存储、明文仅创建时展示一次；公开端点 `POST /openapi/chat`（`Authorization: Bearer hf_xxx`），Redis 固定窗口限流（60/min/Key）+ 按 Key 计费日志
- **表格/网页知识摄入（A3）**：CSV/XLSX 解析器（纯标准库，表格语义化 chunking）+ 注册进解析器工厂；`POST /api/ingest/url` 网页抓取（SSRF 防护、HTTPS-only、2MB 上限、HTML→正文抽取）；Java `POST /document/from-url`；文档页新增"上传文件 / 网页地址"双模式
- **联网搜索（B4）**：web_search 工具支持 DuckDuckGo（免 Key）/ Tavily / Serper（`WEB_SEARCH_*` 环境变量）；`agent.web_search.enabled` flag 门控暴露给 V1 Agent，执行仍受策略引擎（生产禁外网/模式/审批）约束
- **MCP Client 管理（B5）**：运行时注册/重连/移除外部 MCP 服务器，持久化到 `mcp_servers.json`；新页面"MCP 服务"
- **知识库共享（C2）**：`kb_share` 表（V53）；所有者共享/撤销、共享给我的列表；共享用户可对共享 KB 创建对话（Java 侧 4 处 KB 只读校验统一放行）
- **操作审计（C1）**：`audit_log` 表（V54）；公告发布/删除、应用发布/撤回/删除、API Key 创建/删除、KB 共享/撤销均记录审计
- **在线答案评测（C3）**：`POST /api/rag/evaluate/answer-judge` LLM-as-judge 打分（无标准答案模式），Java 代理 `/rag/observability/evaluate/judge`
- **OpenAI 兼容备用供应商（B2）**：`OPENAI_COMPATIBLE_*` 环境变量加入 FailoverLLM 链（通义/Kimi/OpenAI 兼容端点）
- **公告管理（A1）**：管理员公告发布页 + `GET/POST/DELETE /notifications/admin`；通知铃铛接入真实 AgentAlertEvent（此前为待办）
- **实验特性三档治理（A2）**：能力开关页新增"稳定 / 实验 / 冻结"三档；GraphRAG / 多模态 OCR / Multi-Agent / cross_encoder 重排标记冻结；ENVIRONMENT.md 同步

#### Tests
- Java：+20 用例（AppServiceImpl 7、OpenApiServiceImpl 5、KbShareServiceImpl 6、RagObservabilityController judge 2）→ 443
- Python：+34 用例（CSV/XLSX 9、URL 摄入 16、web_search 门控 6、在线评测 3）→ 1266 通过

#### Fixed
- Java 测试环境与本地 `.env`（VECTOR_STORE_MODE=cluster）冲突导致的 4 个环境相关失败已定位为环境差异（CI 无 .env 时通过），非代码回归

## [Unreleased]

### 第五轮优化（2026-08-16）：发布就绪 + Milvus 数据库化 + 仓库清理

#### Added
- **Milvus 数据库化**：Milvus Standalone（2.6.6）+ 外部 etcd（3.5.18）+ Attu 网页控制台（:8000）纳入 dev/prod Compose；数据存于 Docker 卷 `<project>_milvus-data`，`VECTOR_STORE_MODE=cluster` 成为默认
- **发布流水线**：`.github/workflows/release.yml` — 打 `v*` tag 自动构建并推送 4 个镜像到 GHCR（`hfusionhub-{java,python,plugin-runner,frontend}`）+ 生成 GitHub Release；版本升至 `1.0.0`
- **一键启动**：`scripts/init-env.{ps1,sh}`（自动生成随机密钥）与 `scripts/setup.{ps1,sh}`（依赖检查 → 初始化 → 基础设施启动 → 健康等待；`-FullStack` 全容器化）
- **演示数据导入**：`POST /api/demo/import`（admin）一键创建"演示知识库"并向量化 3 篇内置文档；前端 Dashboard 新增 SetupChecklist 引导
- **安全文档**：`SECURITY.md`、`CODE_OF_CONDUCT.md`、`NOTICE`、`.github/dependabot.yml`；CI 增加 gitleaks 与 ruff + pip-audit 门禁；Python 镜像改为非 root 用户
- **前端**：`src/utils/errorMessage.ts` 友好错误提示、`src/api/system.ts` AI 健康检查、Dashboard 展示 AI 服务状态

#### Changed
- **文档合并**：`docs/启动重启1.md` 与 `docs/startup-guide.md` 合并为单一双语 `docs/startup-guide.md`；`docs/FEATURE_FLAGS.md` 并入 `docs/ENVIRONMENT.md`；删除已完成的 `docs/MILVUS_MIGRATION.md`；刷新 ROADMAP/ARCHITECTURE/WHITEPAPER/DR_VECTORS/README/AGENTS/CLAUDE 中过时的 Milvus Lite 表述与测试数
- **脚本清理**：删除一次性阶段性脚本 `scripts/archive/*`（git 历史保留）；修复 `backup_milvus.sh`/`restore_milvus.sh` 的卷名推导（`${COMPOSE_PROJECT_NAME:-deploy}_milvus-data`，原硬编码 `hfusionhub_milvus-data` 与实际不符）
- **本地数据清理**：删除根目录 `uploads/` 残留、过期日志、`chunks_store.json.tmp`、构建/测试产物与全部 `__pycache__`；本地 Milvus Lite 文件（`milvus_data*.db`）已废弃删除，向量数据全部在 Milvus 容器卷中

#### Fixed
- Attu 连接：`MILVUS_URL` 指向 `127.0.0.1:19530`（避免浏览器 `localhost` 走 IPv6 导致 "No connection established"）
- Milvus 2.6 不支持嵌入式 etcd：改用独立 etcd 服务（`ETCD_ENDPOINTS=http://etcd:2379`）

### 第四轮优化（2026-08-07）：Bug 修复与设置页完善

#### Fixed
- **成本仪表板**：修复"最近使用记录"表格永远不会渲染数据行的问题——重构为"模型用量明细"表格，正确遍历 `modelBreakdown` 数据并展示每模型 Token/费用/占比
- **Python runtime API**：`_probe_ollama()` 从同步 `httpx.get()` 改为 `async httpx.AsyncClient`，消除 FastAPI event loop 阻塞；同步更新 `_status_payload()` 和路由处理器为 async/await
- **LLM 探活**：`_is_ollama_available()` 在 async 上下文中通过 `ThreadPoolExecutor` 执行 HTTP 探活，避免阻塞 event loop
- **ReactAgent**：`run()` 和 `_handle_operation()` 中 `assistant_text` / `response` 在 ReAct 循环前初始化为 `None`，消除 `max_steps=0` 时 NameError 风险
- **安全护栏页面**：顶部添加"演示模式"横幅，统计卡片标注"模拟数据 · 非实时"，消除用户将模拟数据误认为真实数据的风险
- **PII 脱敏预览**：正则新增 IPv4 地址匹配

#### Added
- **设置页 → AI 供应商状态卡片**：展示所有已发现供应商（DeepSeek/Ollama/Embedding）的名称、状态徽章、模型和连通性指示；LLM/Embedding/向量库三合一摘要行；刷新按钮 + 最近检查时间

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
