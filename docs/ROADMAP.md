# 路线图

> HFusionHub project roadmap — updated quarterly.
> This document merges the former ROADMAP.md and the PROJECT_ASSESSMENT.md snapshot (2026-08-18) into a single roadmap with historical evaluation records.

## Current Status (2026-08)

- **Core**: Stable — Auth, KB CRUD, document upload/parsing, chat with RAG
- **RAG**: Stable — Vector + BM25 hybrid retrieval with RRF; Milvus Standalone + external etcd (cluster 模式), Attu 网页控制台查看向量数据
- **Agent**: Stable — ReAct loop with tool calling, SSE streaming
- **MCP**: 7 tools exposed via JSON-RPC 2.0
- **Memory**: Persistent entity facts, summaries, user preferences (V8)
- **Notifications**: System notice table + read tracking (V9)
- **Production**: Docker Compose prod (MySQL/Redis/MinIO/Milvus/etcd/Attu/Java/Python/Plugin Runner), Helm chart, GHCR 镜像发布流水线（`v*` tag 自动构建推送）
- **Release**: 版本 1.0.0；`scripts/setup.ps1/.sh` 一键启动 + `init-env` 自动生成随机密钥；演示数据一键导入；Setup 引导清单
- **Tests**: Python 1556 ✅ | Java 703 ✅（单测 H2 + 集成 Testcontainers，见 ADR-008） | Frontend 77 单测 + 73 E2E ✅（2026-09-08 口径）
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
- [x] **Dynamic feature flags** — DB 驱动 `feature_flag` + 规则；Java→Python snapshot 同步 8 flags（`agent.enabled` / `write_tools` / `web_search` 等）
- [x] **E2E tests** — Playwright 覆盖登录/知识库/文档/对话/审批/写笔记等关键路径（`e2e/write-note.spec.ts` 3 项）
- [x] **Theme system** — light/dark/system 三档 + 服务端偏好同步（`sys_user.theme_preference` V57；登录时 `getUserInfo()` 远端优先，换设备自动应用）
- [x] **SSO/OIDC** — 通用 OIDC 客户端（授权码流程：`/user/sso/authorize`+`callback`、V60 绑定列、前端按钮与落地页，见 [docs/OIDC.md](OIDC.md)）；默认关闭，经 `app.oidc.*` 对接外部 IdP 启用

## Phase 5 — 写笔记闭环 + 工程化补课（2026-08-18）✅

- [x] **写笔记闭环（P0–P4）** — `note` 表（V55）+ 用户笔记 API + Python `write_note` 真实持久化 + 审批门控（approval_required）+ 前端确认卡片 + 「我的笔记」页面
- [x] **模型用量接通** — 聊天/Agent/开放 API 均落 `model_usage_record`，/cost 页面有真实数据
- [x] **全栈冒烟脚本** — `scripts/smoke-test.ps1`（41 项，含核心链路）
- [x] **静态一致性校验** — `scripts/static-checks.py` 租户列完整性 + token 键一致性（CI `static-consistency` job）
- [x] **Agent 工作流回归** — `scripts/verify-agent-workflow.ps1`（5 项）
- [x] **意图分类写操作** — "保存/整理成笔记"→ operation 意图（工具触发率提升）
- [x] **web_search 工具修复** — 嵌套 Topics + lite HTML fallback
- [x] **管理端审计视图** — `/admin/audit-logs/operations` + `/cross-tenant`
- [x] **修复** — kb_share/app_api_key 缺 tenant_id（V56）、FeatureFlag snapshot token 键、workflow 白名单漏 write_note、waiting_approval 状态映射
- [x] **生产核对清单** — `docs/PRODUCTION_CHECKLIST.md`（已并入 [PRODUCTION_OPS.md](PRODUCTION_OPS.md)）

## Phase 6 — 2026-08-19 交付与建议方向

### 已交付（2026-08-19）

- [x] **各菜单一键导入示例数据** - `/demo/import` 覆盖知识库/回答方案/笔记/记忆/应用/公告 6 个菜单（幂等分项计数，导入后按菜单显示新增/已存在）；`/demo/clear` 一键清除（软删除，7 天可恢复）；MCP 服务页空状态 CTA 直接预填示例并打开表单；工作台统计失败展示具体原因 + 重试
- [x] **真实 DeepSeek API Key 配置** — `python-ai/.env` 已写入真实 key（`deepseek-v4-flash`），流式聊天实测通过（"你好呀！很高兴能和你聊天…"）
- [x] **冒烟测试全绿** — `scripts/smoke-test.ps1` **48 PASS / 0 FAIL**（修复演示数据清空端点为 `POST /demo/clear`、DeepSeek 探测 cwd、文档解析响应捕获 3 处脚本缺陷）
- [x] **CORS 支持配置化/任意 Origin** — `app.cors.allowed-origins`：修复内网穿透（cpolar 动态域名）下浏览器登录 403；开发/穿透默认放行，生产可配置白名单收紧
- [x] **公网访问改用生产预览** — vite preview + preview.proxy：dev 模式 33 模块经公网逐模块加载需 40s，打包产物 <4s 渲染
- [x] **隧道 URL 查询脚本** — `scripts/get-tunnel-url.ps1` 一键查询 cpolar 当前公网 URL（隧道重连后 URL 变化时使用）
- [x] **文档体系整合** — WHITEPAPER→ARCHITECTURE、PROJECT_ASSESSMENT→ROADMAP、PRODUCTION_CHECKLIST+DR_VECTORS→PRODUCTION_OPS、PERFORMANCE_BASELINE→SCALING；删除 PROJECT_SUMMARY；README 新增文档索引（见 [README.md](../README.md)）

### 待排期

- [x] **逐功能后续优化方案** — [docs/OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md)：三大模块 P0/P1/P2 优化清单已全部交付（2026-08-20）；后续第十六轮（R16）方案见下方 Phase 7
- [x] **Plugin Runner TLS** — 主机级 Docker daemon TLS 配置 + `scripts/generate-runner-tls.sh`（见 `docs/PLUGIN_RUNNER_TLS.md`）
- [x] **eval-nightly 启用** — GitHub `vars.EVAL_BASE_URL` + `secrets.EVAL_INTERNAL_TOKEN` 已配置；⚠️ 免费版 cpolar 隧道每次重启随机子域名（需 `scripts/get-tunnel-url.ps1` 刷新 URL），且隧道须在 nightly 定时（02:00 UTC）时在线——落地指引（R15-27）：cpolar 面板升级保留隧道获得固定子域名，或注册为 Windows 服务 `sc create cpolar binPath= "...cpolar.exe http 9000" start= auto`；固定的 EVAL_BASE_URL 填入 GitHub Actions Variables 后 nightly 不再依赖人工在线
- [x] **多 Agent 协作解锁** — `agent.multi_agent.enabled` 默认开启（Flyway V59），前端「能力开关」页解冻为实验态，「复杂任务」预设同步开启；收益验证见 nightly 评测
- [x] **租户配额计费展示** — `/api/quota/summary`（QuotaController + QuotaSummaryDTO）→ /cost 页配额面板（用量条 70%/90% 分级告警）

## Phase 7 — R16 优化（2026-09，进行中）

> 方案全文见 [docs/OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md) 第十六轮（R16，2026-09-08 复审）。均衡推进四批：

- [x] **批次 1 基线与一致性收口（R16-P0）** — runtime 基线重冻结 ✅（2026-09-09 真机跑批：拒答 0.625→0.9625，检索指标口径变化归因见 CI_GATES 注记）、ADR-001~005 补写 ✅、仓库卫生 ✅、状态对账 ✅；附带修复 pymilvus 版本漂移（4 测试转绿）与检索调试快照空内容崩溃
- [x] **批次 2 性能达标（R16-P1，仅应用层）** — query embedding 缓存（同请求复用 + 跨请求缓存）✅、文档嵌入批量 32×并发 2 配置化 ✅、SSE 线程池容量对齐并发流数 + MDC 传播 ✅、N+1 三处批量预取 ✅、无界查询审计收口 ✅（延迟复测待本机服务栈可用后留档）
- [x] **批次 3 质量加固（R16-P2）** — 覆盖率棘轮（Java BRANCH 0.34 + Python fail-under 74）✅、IT 无 Docker 跳过机制修复（ExecutionCondition 前置裁决，本机 701 过 BUILD SUCCESS）✅、ACL 越权回归矩阵 13 例入测试库 ✅（并修复 3 个直读端点真实缺陷：404 语义 + 两处 outline_path 解析）；剩余：2 个 IT 类真库迁移（独立小迭代，Docker 双向验证已完成 703 过）
- [x] **批次 4 评测与工程卫生（R16-P3）** — 结构化 JSON 日志双端落地（Java json-logs profile + Python LOG_FORMAT=json，顺带修复 trace_id 恒为 "-" 的 filter 挂载缺陷）✅、前端共享组件单测首批（MarkdownRenderer XSS 面 + ConfirmDialog）✅、ENVIRONMENT.md 补 SSE 池/日志键 ✅、chat 发送单飞状态机收口（useChatSending，手工置位清零 + retry/regenerate 守卫全程覆盖，前端 77 单测）✅；剩余待真机/下批：答案标注率定位与 tool_calls 稳定性（需模型栈）、消息列表 store 化与页面组件拆分、运维债真机项

---

## 附：2026-08-18 项目评估快照（历史记录）

> 原 PROJECT_ASSESSMENT.md 全文存档。评估日期：2026-08-18；评估方式：全栈启动 + 功能冒烟测试（API 级）+ 核心链路实测。

### 评估方法与范围

| 层 | 验证方式 | 覆盖 |
|---|---|---|
| 基础设施 | `docker compose ps` 健康检查 | MySQL / Redis / MinIO / Milvus / etcd / Attu / Plugin Runner |
| Java 后端 | 登录后 31 项 API 冒烟（全部 controller 模块） | 认证、知识库、文档、对话、Agent、审批、记忆、用量、笔记、插件、提示词、MCP、RAG 可观测、系统、功能开关、通知、共享、模型配置 |
| Python AI | 8 项健康/能力检查 + RAG 实测 | health、gateway、工具注册表、MCP、RAG 检索、Agent 聊天 |
| 核心链路 | 端到端实测 | 文档上传→解析→分块→向量化→检索→知识库问答引用；聊天用量落账；写笔记审批触发 |
| 前端 | 页面加载 + 路由文件完整性 + Vite 编译 | 24 个页面文件、SPA 挂载 |

### 功能验证结果矩阵（2026-08-18）

**基础设施（6/7，86%）**：MySQL ✅ healthy（Flyway V1–V56）、Redis ✅、Milvus Standalone ✅（18 chunks 入库）、etcd ✅、MinIO ✅、Attu ✅ running；**Plugin Runner ⚠️ unhealthy**（Docker TLS 证书未配置，见下）。

**Java 后端 API（31/31，100%）**：认证/知识库（共享本轮修复 V56）/文档（18 chunks COMPLETED）/对话/Agent/记忆/用量（本轮修复，原永远为 0）/笔记/插件/提示词/MCP/RAG 可观测/系统/功能开关/通知/模型配置 全部 ✅。

**Python AI（12/12，100%）**：health、runtime、gateway、工具注册表（write_note 可见）、MCP、RAG debug/search（3 条 score 0.99）、Agent V1 聊天（3 来源引用）✅。

**核心链路（6/6，100%）**：文档处理闭环、检索引用问答、聊天用量落账、写笔记审批触发、写笔记持久化、Feature flag 同步 8 flags ✅。

### 目标达标对照

| 指标 | 目标 | 实测 | 达标 |
|---|---|---|---|
| 后端 API 可用率 | 100% | 100%（31/31） | ✅ |
| 基础设施健康率 | 100% | 86%（6/7） | ⚠️ plugin-runner |
| 文档处理成功率 | 100% | 100%（18/18 chunks） | ✅ |
| 检索相关性（Top-1 score） | ≥ 0.90 | 0.99 | ✅ |
| 用量数据可用 | 有数据 | 有（真实 token） | ✅ |
| 功能覆盖率（已交付 vs 代码存在） | 100% | 100% | ✅ |

### 当时发现并修复的问题

**本轮修复（3 项）**：

| # | 问题 | 修复 |
|---|---|---|
| 1 | `kb_share`、`app_api_key` 表缺 `tenant_id` 列 → 共享/开放 API Key 功能整体 500 | **V56 迁移**补列 + 回填 + 索引；复测通过 |
| 2 | 模型用量链路从未接通（`CostTrackingService.record()` 无调用方）→ /cost 永远为 0 | Java 聊天/Agent 完成时落账（含流式估算） |
| 3 | Feature flag snapshot 鉴权键错误（`${app.internal-token}` 未定义）→ Python 拉到 0 flags | 改为 `${python-ai.internal-token}`，实测同步 8 flags |

**遗留（需外部配置/产品决策）**：
1. **Plugin Runner unhealthy**（容器内 Docker TLS 证书缺失）→ 运行 `scripts/generate-runner-tls.sh deploy/runner-tls`（指引见 [PLUGIN_RUNNER_TLS.md](PLUGIN_RUNNER_TLS.md)）
2. **默认 LLM 为 Ollama（qwen2.5:3b）**：工具调用不稳定 → 已解决（2026-08-19 配置真实 DeepSeek key 后聊天默认路由 DeepSeek）
3. `notebooks/rag_evaluation.ipynb` API 路径过时 → 已修复（`debug-search`→`debug/search`）
4. 测试数据残留（KB 52 演示文档等）→ 可 `POST /api/demo/clear` 清理

### 总体评估结论

**平台功能完整、核心链路可用，处于"功能齐全但深度与工程化待补"阶段。**

**优势**：架构清晰（CQRS 式 Java/Python 分层，工具注册表+策略引擎+审批门控）、功能覆盖面广（RAG/Agent/插件/MCP/开放 API/租户/用量成本）、可靠性机制（Flyway、幂等索引、孤儿恢复、租户拦截器）、可观测（RAG traces、Agent dashboard、用量成本、告警规则）。

**短板（暴露的问题模式）**：① 建表遗漏类问题（V52/V53 缺 tenant_id）说明多租户表覆盖检查不足 → 已加 CI 静态校验；② "代码存在但未接线"（用量、feature flag 键、write_note 白名单）→ 已有冒烟/契约测试兜底（47 项全绿）；③ 模型依赖（Ollama 3B 意图分类/工具调用质量）→ 已切换 DeepSeek；④ 插件沙箱未就绪。

### 下一步建议（方向性结论）

按"先稳后深再变现"排序：**当前最大杠杆是"把已有能力的开关全部接通并加验证门禁"，而非新增功能**；之后把模型路由切到强模型（已实现），工具与多 Agent 能力即可兑现为可演示的差异化价值。

- P0 可靠性补课（已完成）：Plugin Runner TLS 接入；CI 静态校验（租户列完整性、token 键一致性）；冒烟脚本固化进 CI
- P1 AI 能力深度（已完成）：默认模型路由切换 DeepSeek；Agent workflow 回归验证（5/5）；web_search 启用 + bug 修复
- P2 评测与质量闭环（已完成）：在线评估门禁（eval_offline CI + eval_runtime nightly）；意图分类写操作样例；Playwright E2E（write-note 3/3）
- P3 商业化与工程化（已完成）：开放 API 计费打通；多租户审计视图；生产部署要点清单（PRODUCTION_CHECKLIST → 已并入 PRODUCTION_OPS）

---

*HFusionHub — Built with Java's reliability and Python's AI ecosystem.*
