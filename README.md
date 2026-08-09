# HFusionHub

> 个人开源项目 — Java + Python 混合架构的多租户 AI Agent 平台（RAG + Agent + 插件沙箱 + 大数据运营分析）

[English](./README_EN.md) | 简体中文

![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)
![Java](https://img.shields.io/badge/Java-17%2B-orange)
![Python](https://img.shields.io/badge/Python-3.11%2B-green)
![Vue](https://img.shields.io/badge/Vue-3-42b883)
![Tests](https://img.shields.io/badge/Tests-Python%201451%20%7C%20Java%20702%20%7C%20Frontend%2057-success)

## 这个项目是什么（30 秒版）

HFusionHub 是一个可以私有部署的 AI Agent 平台：上传文档建知识库（RAG 问答、带引用溯源）、ReAct Agent 执行多步任务（敏感工具需人工审批）、插件在沙箱里运行、全程有用量计费与审计。它有意采用 **Java 管写入、Python 管智能**的双语言分层架构——用两个生态各自最擅长的一面，同时逼自己解决跨语言一致性问题。

## 核心工程点（面试官视角）

- **双语言三层的职责切分**：Java（Spring Boot 3.5.16）独占全部 MySQL 写路径（ACID、多租户、计费账本），Python（FastAPI）独占检索与 Agent 智能；两端之间用内部令牌 + HMAC 签名回调约束契约，`scripts/static-checks.py` 在 CI 里静态校验契约锚点。
- **工具审批的正确性设计**：审批决定的三表更新在同一事务内完成，签发**一次性执行令牌**（数据库守卫 UPDATE 保证 exactly-once），LLM/工具执行经 afterCommit 移出事务——行锁不会被 120 秒的工具调用占住。
- **并发与竞态治理**：任务状态机全部走条件 UPDATE 守卫迁移（completeRunGuarded / failUnlessTerminal），用量账本"只有赢得终态迁移的一方结算"，配套竞态回归测试。
- **RAG 管线纵深**：意图分类 → 查询分解 → 多路检索（向量+BM25+图谱+RRF）→ 上下文压缩 → 检索证据门（低置信拒答）→ Groundedness 守卫与重试 → 引用完整性校验；答案逐论断 `[n]` 引用溯源；Parent-Child 父子分块与语义分块（实验档）提升长文档召回。
- **测试与防漂移门禁**：Java 702（H2 内存库 + Flyway 校验）/ Python 1451 / 前端 57 单测 + 73 E2E；schema-h2 与迁移链**漂移零容忍**（漏同步直接 CI 红）、文档测试计数与代码强同步、离线评测门禁（recall/nDCG/引用 P·R·F1 基线，引用窗口按相关性自适应，见 [ADR-006](docs/adr/ADR-006-faithfulness-metric-recalibration.md)）。
- **数据规模**：84 个 Flyway 迁移、26 轮自审修复批次（全部记录在 CHANGELOG）、48 项冒烟自测全过。

## 质量与验证口径（如实）

- 全部功能经过**本地 Docker Compose 全链路自测**（冒烟 48 PASS / 0 FAIL），上述三端测试套件本地全绿。
- **未经过生产环境流量验证**；`deploy/` 下的生产部署配置与 `docs/PRODUCTION_OPS.md` 运维手册是"可部署起点"，不是"生产验证结论"。

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端界面层                              │
│         (Vue 3 + Vite + TypeScript + Tailwind)           │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP/WebSocket
┌─────────────────────▼───────────────────────────────────┐
│                 Java 后端服务层                           │
│        (Spring Boot 3.5.16 + MyBatis Plus)               │
├─────────────────────────────────────────────────────────┤
│  • 用户认证 (JWT + Sa-Token)                             │
│  • 知识库管理 (CRUD、权限)                                │
│  • 对话记录 (MySQL)                                      │
│  • 知识来源持久化                                         │
│  • 调用Python AI服务 (HTTP)                              │
│  • 流式输出转发 (SSE)                                     │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP
┌─────────────────────▼───────────────────────────────────┐
│                Python AI Agent 层                        │
│                   (FastAPI)                              │
├─────────────────────────────────────────────────────────┤
│  • ReAct Agent循环        • 工具调用系统                  │
│  • RAG检索引擎            • 会话记忆管理                  │
│  • 向量数据库 (Milvus Standalone + Attu) • 流式输出 (SSE)                │
│  • LLM调用 (DeepSeek/Ollama/OpenAI兼容)  • 多模型路由 + 降级      │
│  • 知识来源格式化                                       │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                    数据存储层                             │
├─────────────────────────────────────────────────────────┤
│  • MySQL 8.0 (用户、知识库、对话、知识来源)               │
│  • Redis 7.x (缓存、会话、限流)                           │
│  • Milvus Standalone (向量存储, Attu 可视化)                       │
└─────────────────────────────────────────────────────────┘
```

## 📋 功能模块

### 1. 知识库管理（Java + Python）
- 文档上传（PDF、DOCX、TXT、Markdown）→ Apache Tika 解析 → 分块（固定窗口 / 父子 / 语义）→ 向量化入库
- 知识库 CRUD + 回收站、权限管理 + 多租户隔离

### 2. Agent 核心（Python）
- ReAct 循环（意图识别 → 工具调用 → 审批拦截 → 自我反思）
- 多 Agent 协作（retrieval / analysis / critic / synthesis）
- 工具审批工作流（一次性执行令牌 + 审计追踪）
- 流式输出（SSE + 结构化 step_completed / approval_required 事件）
- Checkpoint 持久化（暂停/恢复/重试）、观测（Trace、告警、恢复调度）、评测（数据集、Case、Run）

### 3. RAG 引擎（Python）
- 意图分类 → 自适应检索规划 → 查询分解 → 并行子问题执行
- 多路检索（向量 + BM25 + 图谱 + RRF 融合）
- 上下文压缩 + 证据完整性守卫 + Groundedness 回退重试
- 自我反思 + 回答质量评测 + 引用溯源

### 4. 工具系统（Python + MCP）
- 7 个内置工具 + MCP JSON-RPC 2.0 外部工具
- 工具注册表（风险等级、权限门控、超时、版本门控）
- 插件沙箱（独立 Runner 进程 + TLS + digest 校验）

### 5. 构建中心（Java + 前端）
- Prompt 工作台（版本快照 + 一键回滚 + 乐观锁 409）
- 模型中心、工具中心、方案测试台 + 回归用例集批量验证

### 6. 模型网关（Python）
- 多供应商：DeepSeek / Ollama / OpenAI 兼容
- 自动降级链 + 熔断器 + Token 桶速率限制
- Token 用量累加 → Java 成本追踪与配额账本

### 7. 对话与运营（Java + Python + 前端）
- 多轮对话 + SSE 流式 + 会话/长期记忆
- 成本仪表板、RAG 观测、通知告警
- 运营数仓扩展包（Hadoop/Hive/Spark/Flink，见 docs/BIGDATA_ARCHITECTURE.md）

## 🚀 快速开始

### 一键启动（推荐，Windows / Linux / macOS）

```bash
# Windows PowerShell
.\scripts\setup.ps1            # 基础设施 + 开发指引（三终端热重载）
.\scripts\setup.ps1 -FullStack # 全部容器化，一条命令启动完整平台

# Linux / macOS
bash scripts/setup.sh          # 基础设施 + 开发指引
bash scripts/setup.sh --fullstack  # 全部容器化
```

脚本会自动：检查 Docker 前置依赖；生成强随机口令写入 `docker/.env` 等文件；启动基础设施（MySQL / Redis / MinIO / Plugin Runner）并等待健康；`-FullStack` 模式继续构建/拉取应用镜像并启动全平台。

### 手动启动（开发热重载）

环境要求：Java 17+、Python 3.11+、Node.js 20.19+/22.12+（Vite 8 要求）、Docker（MySQL/Redis/Milvus）。

```bash
git clone https://github.com/xiaodu55/HFusionHub1.git
cd HFusionHub1
# 必须使用自己的随机值；请勿提交 .env 文件
export MYSQL_ROOT_PASSWORD='replace-with-a-strong-password'
export MYSQL_PASSWORD='replace-with-a-strong-password'
export PLUGIN_RUNNER_TOKEN='replace-with-a-long-random-token'
export CALLBACK_SECRET='replace-with-a-long-random-secret'
export PYTHON_AI_INTERNAL_TOKEN='replace-with-a-second-long-random-secret'
export ADMIN_PASSWORD='replace-with-a-strong-admin-password'
cd docker && docker compose up -d
```

数据库启动后，三个终端分别运行：

```bash
# 终端 1：Java 后端
cd java-backend && mvn spring-boot:run

# 终端 2：Python AI 层
cd python-ai
python -m venv .venv && .venv/Scripts/Activate.ps1   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.main

# 终端 3：前端
cd hfusionhub-frontend && npm ci && npm run dev
```

**服务端口**：

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端 (dev) | 3000 | Vite开发服务器 |
| 前端 (prod) | 80 | Nginx静态服务 |
| Java 后端 | 8080 | Spring Boot |
| Python AI | 9000 | FastAPI |
| MySQL | 3306 | Docker容器 |
| Redis | 6379 | Docker容器 |
| MinIO | 9001, 9002 | 对象存储（控制台, API） |
| Plugin Runner | 9100 | 插件沙箱执行 |
| Milvus | 19530, 9091 | 向量数据库（Standalone + etcd） |
| Attu (Milvus 控制台) | 8000 | 浏览器查看向量数据 |

**启动后访问**：
- 前端：http://localhost:3000
- Java API：http://localhost:8080
- Python AI 健康检查：http://localhost:9000/health（业务接口仅接受 Java 服务携带的内部令牌）
- API 文档：http://localhost:8080/api/doc.html（Knife4j / Swagger UI）

### 默认账号
- 用户名：admin
- 密码：由 `ADMIN_PASSWORD` 决定

### 一键演示数据

基础设施启动并登录后，可一键导入演示数据（知识库文档、回答方案、笔记、记忆、公告等），直接体验 RAG 全链路：

```bash
curl -X POST http://localhost:8080/api/demo/import   -H "satoken: <登录后获取的token>"
curl -X POST http://localhost:8080/api/demo/clear -H "satoken: <token>"   # 清空
```

> 演示端点默认关闭，开发 compose 已开启（`DEMO_ENDPOINTS_ENABLED=true`）；生产 compose 默认不可用（`/demo/clear` 有数据破坏性）。

## 🚢 部署

### 从预构建镜像部署

镜像发布在 GitHub Container Registry（`ghcr.io/xiaodu55/hfusionhub-{java,python,plugin-runner,frontend}`），打 `v*` tag 时由 CI 自动构建推送。

```bash
cp deploy/.env.example deploy/.env   # 编辑填入密钥；或运行 scripts/init-env.ps1 自动生成
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d
# 访问 http://localhost（前端 :80）
```

> 如实说明：该部署配置已通过**本地**容器化自测，未经过生产环境流量验证。
> 运维手册见 [docs/PRODUCTION_OPS.md](docs/PRODUCTION_OPS.md)，监控（Prometheus/Grafana）见 `deploy/docker-compose.monitoring.yml`。

## 🧠 RAG 引擎模块

| 模块 | 功能 | 测试数 |
|------|------|--------|
| IntentClassifier | 意图识别 | - |
| QueryDecomposer | 查询分解 | 35 |
| ContextCompressor | 上下文压缩 | 43 |
| SelfReflector | 自我反思 | 36 |
| QueryRouter | 智能检索路由 | 42 |
| MultiTurnStrategy | 多轮检索策略 | 45 |
| KnowledgeGraph | 知识图谱 | 59 |
| Utils | 公共工具 | 36 |

## 🧩 高级功能矩阵

| 功能 | 状态 | 默认 | 依赖 |
|------|------|------|------|
| Hybrid Retrieval (Vector + BM25) | ✅ Stable | 开启 | 无额外依赖 |
| GraphRAG (Scoped) | 🧪 Beta | 关闭 | `RAG_GRAPH_ENABLED=true` + 图谱索引 |
| Reranker (第二-stage) | 🧪 Beta | 关闭 | `RAG_RERANKER_MODE=lexical/cross_encoder` |
| Multimodal / OCR | 🔬 Experimental | 关闭 | Tesseract + `requirements-multimodal.txt` |
| Single-Agent Workflow | 🧪 Beta | 关闭 | `RAG_AGENT_WORKFLOW_ENABLED=true` |
| Multi-Agent Collaboration | 🔬 Experimental | 关闭 | 依赖 P9 + 明确选中的知识库 |

> 详见 [python-ai/.env.example](python-ai/.env.example) 和 [docs/python-ai.md](docs/python-ai.md#feature-flags)

## 📖 文档索引（Documentation Index）

> 所有文档位于 [docs/](docs/) 目录，按用途分三类：**开发**、**运维**、**治理**。
> 关键事实基线：Java 702 测试 / Python 1451 / 前端 57 单测 + 73 E2E / Flyway V84 / Spring Boot 3.5.16。
> 离线评测基线（suite 1.1.0，2026-09-05 冻结，引用模拟含压缩感知）：Recall@5=0.932 / nDCG@10=0.903 / 引用准确率=0.942 / 引用忠实度 F1=0.741（精确率 0.703、召回率 0.894）。答案逐论断引用 `[n]` 标注经 `cited_chunk_ids` 透出，runtime 轨按答案实际标注的引用计分。

### 开发类

| 文档 | 作用 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **架构全景**。CQRS 三层架构图、数据流、关键设计决策、安全边界、设计模式、与 Dify/Ragent/LangChain 对比 |
| [docs/PROJECT_TOUR.md](docs/PROJECT_TOUR.md) | **项目功能全览**（带截图）：每个页面的功能说明与使用方法，新用户与评估者首选入口 |
| [docs/java-backend.md](docs/java-backend.md) | Java 后端开发指南：项目结构、设计模式、环境变量、Flyway 规则（V1–V84）、测试与构建 |
| [docs/python-ai.md](docs/python-ai.md) | Python AI 开发指南：模块结构、RAG 管线、Feature Flags、SSE 输出格式、Provider 说明 |
| [docs/BIGDATA_ARCHITECTURE.md](docs/BIGDATA_ARCHITECTURE.md) | **HFusionData Analytics**（分析扩展包）：Hadoop 运营数仓架构、数据字典、部署/运维手册、演示动线 |
| [docs/database.md](docs/database.md) | 数据库设计：V1–V84 全部迁移历史、核心表、实体关系、迁移规则 |
| [docs/api.md](docs/api.md) | API 接口参考：模块列表、公开端点、调用约定 |
| [docs/agent-v1-scope.md](docs/agent-v1-scope.md) | Agent V1 软件契约：只读研究型 Agent 的能力边界、输入/输出 JSON 契约 |
| [docs/SWAGGER_UI.md](docs/SWAGGER_UI.md) | Swagger UI 配置指南：访问地址、生产关闭/IP 白名单/Basic Auth 策略、注解规范、常见问题 |
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | **环境变量清单（唯一权威）**：Docker/Java/Python 全部变量、Feature Flags（P5 稳定开、实验默认关、冻结保持关） |

### 运维类

| 文档 | 作用 |
|------|------|
| [docs/ACCESS_MAP.md](docs/ACCESS_MAP.md) | **已启动服务全量访问地图**：浏览器网址、登录凭据、API 文档（Knife4j/FastAPI）、Java 238 接口分组、Python 67 路由、前端 36 页面 |
| [docs/startup-guide.md](docs/startup-guide.md) | **启动/重启/排障双语指南**（中英对照）：首次安装、一键启动、日常启动顺序、重启决策表、数据库重置、部署注意 |
| [docs/PRODUCTION_OPS.md](docs/PRODUCTION_OPS.md) | **部署运维手册**：部署检查清单、Runner TLS、插件 digest、配额账本、Agent 故障定位、向量库容灾、Staging 演练 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 故障排查手册：P0 服务不可用 / P1 功能异常 / P2 性能 / P3 非关键，含数据恢复与日志收集 |
| [docs/FAQ.md](docs/FAQ.md) | 常见问题速查：菜单为空、插件 runner、演示数据、忘记密码、检索通道数等 |
| [docs/SCALING.md](docs/SCALING.md) | **扩容与性能手册**：扩容决策矩阵、垂直/水平扩容、K8s/Helm、性能基线测试、监控告警、成本优化 |
| [docs/PUBLISH_CHANNELS.md](docs/PUBLISH_CHANNELS.md) | **发布渠道**：可嵌入聊天挂件（/embed/chat）+ 飞书/钉钉/企微机器人接入与安全要点 |
| [docs/GRAPHRAG_REVIEW.md](docs/GRAPHRAG_REVIEW.md) | **GraphRAG 数据驱动复评结论**：cross_document 基线数据、不立项结论与重开条件 |
| [docs/PLUGIN_BUILTINS.md](docs/PLUGIN_BUILTINS.md) | **平台内建插件**：provision 管线（wheel→签名→镜像→dind→digest 回填）、dev 沙箱解锁、租户可见性、e2e 验收 |
| [docs/PLUGIN_RUNNER_TLS.md](docs/PLUGIN_RUNNER_TLS.md) | Plugin Runner TLS 配置指引（dev compose dind sidecar 默认解锁 + rehearsal/宿主 daemon 备选路径） |

### 治理类

| 文档 | 作用 |
|------|------|
| [docs/ROADMAP.md](docs/ROADMAP.md) | **路线图**：当前状态、Phase 0–6 完成情况、评估快照存档 |
| [docs/OPTIMIZATION_PLAN.md](docs/OPTIMIZATION_PLAN.md) | **逐功能后续优化方案**：三大模块 P0/P1/P2 优化清单，含文件路径、问题、方案、优先级 |
| [docs/CI_GATES.md](docs/CI_GATES.md) | CI 门禁：Compose 校验、Python/Java/前端测试、离线评测门禁（PR 阻塞） |
| [docs/SECURITY_REGRESSION.md](docs/SECURITY_REGRESSION.md) | 安全回归清单：每日/每次发布必查的 5 条安全边界（租户隔离、HMAC 回调、插件沙箱、配额幂等、租户拒绝执行） |
| [docs/BID_COMPLIANCE.md](docs/BID_COMPLIANCE.md) | **招投标合规与责任边界**：机密性（tenant_id 隔离/SSE 同租户/知识库边界）、准确性（逐节强制审批/critical 人工确认/引用追溯）、审计与私有部署 |

## 🤝 贡献

欢迎参与贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

## 📄 许可证

Apache-2.0 许可证。详见 [LICENSE](LICENSE) 文件。
