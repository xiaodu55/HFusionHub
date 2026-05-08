# HFusionHub

> Java + Python 混合架构的 AI Agent 智能助手平台

![CI](https://github.com/xiaodu55/HFusionHub1/actions/workflows/ci.yml/badge.svg)
![E2E](https://github.com/xiaodu55/HFusionHub1/actions/workflows/e2e.yml/badge.svg)
![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)
![Java](https://img.shields.io/badge/Java-17%2B-orange)
![Python](https://img.shields.io/badge/Python-3.11%2B-green)
![Vue](https://img.shields.io/badge/Vue-3-42b883)
![Tests](https://img.shields.io/badge/Tests-Python%201220%2B%20%7C%20Java%20445%20%7C%20Frontend%2033-success)

## 🚀 项目简介

HFusionHub 是一个企业级 AI Agent 平台，结合 Java 后端的稳定性和 Python AI 的灵活性，提供完整的 RAG + Agent 解决方案。

### 核心特性

- **Java 后端**：Spring Boot 3.x + MyBatis Plus + MySQL + Redis
- **Python AI 层**：FastAPI + Milvus Standalone（Docker/生产，Attu 可视化；本地裸跑可选 Lite）
- **Agent 核心**：ReAct 循环、多 Agent 协作、工具审批、Checkpoint、流式输出、结构化事件
- **RAG 引擎**：多路检索、向量召回、语义分块、知识图谱、查询分解、上下文压缩、自我反思、证据完整性校验
- **Web 界面**：Vue 3 + Vite + TypeScript + Tailwind CSS
- **模型网关**：DeepSeek / Ollama / OpenAI 兼容，自动降级、熔断、速率限制、Token 计费
- **构建中心**：Prompt 工作台（版本历史与回滚）、模型中心、工具中心、插件管理
- **运营中心**：成本仪表板、工具审批、RAG 观测、长期记忆
- **安全护栏**：Prompt 注入检测、内容审核、PII 脱敏（演示模式）

## 📋 功能模块

### 1. 知识库管理（Java + Python）
- 文档上传（PDF、DOCX、TXT、Markdown）
- 文档解析（Apache Tika）
- 知识库 CRUD + 回收站
- 权限管理 + 多租户

### 2. Agent 核心（Python）
- ReAct 循环（意图识别 → 工具调用 → 审批拦截 → 自我反思）
- 多 Agent 协作（retrieval / analysis / critic / synthesis）
- 工具审批工作流（approve/reject + 审计追踪）
- 流式输出（SSE + 结构化 step_completed / approval_required 事件）
- Checkpoint 持久化（暂停/恢复/重试）
- Agent 观测（Trace、告警、恢复调度）
- Agent 评测（数据集、Case、Run）

### 3. RAG 引擎（Python）
- 意图分类（IntentClassifier）→ 自适应检索规划
- 查询分解（QueryDecomposer）→ 并行子问题执行
- 多路检索（向量 + BM25 + 图谱 + RRF 融合）
- 上下文压缩（ContextCompressor）+ 证据完整性守卫
- 自我反思（SelfReflector）+ 回答质量评测
- Groundedness 回退：压缩导致证据丢失时自动用原始上下文重试

### 4. 工具系统（Python + MCP）
- 7 个内置工具：search_knowledge_base, read_chunk, list_document_chunks, calculator, time, web_search, write_note
- MCP JSON-RPC 2.0 协议支持
- 工具注册表（风险等级、权限门控、超时、版本门控）
- Tool Calling 白名单 + 执行策略引擎

### 5. Prompt 工作台（Java + 前端）
- 模板 CRUD + 发布/撤回生命周期
- 版本快照（prompt_template_version）+ 一键回滚
- 乐观锁并发保护（版本冲突 → HTTP 409）
- 测试台 + 测试用例集批量回归

### 6. 模型网关（Python）
- 多供应商：DeepSeek / Ollama / OpenAI 兼容
- 自动降级链 + 熔断器 + Token 桶速率限制
- Token 用量累加器 → Java 后端成本追踪
- 模型别名解析（provider:model 显式路由）

### 7. 对话管理（Java + Python）
- 多轮对话 + SSE 流式
- 会话记忆 + 长期记忆持久化
- 上下文管理 + 知识来源引用显示

### 8. 成本与运营
- 成本仪表板（汇总、日趋势、模型分布）
- Agent 任务执行中心（状态过滤、重试、取消）
- RAG 观测（检索评估、质量评分）
- 通知与告警（Agent 失败率、引用缺失率）

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端界面层                              │
│         (Vue 3 + Vite + TypeScript + Tailwind)           │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP/WebSocket
┌─────────────────────▼───────────────────────────────────┐
│                 Java 后端服务层                           │
│            (Spring Boot 3.x + MyBatis Plus)              │
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

## 📁 项目结构

```
HFusionHub/
├── java-backend/                  # Java 后端
│   ├── src/main/java/com/hfusionhub/
│   │   ├── config/                # 配置类
│   │   ├── controller/            # 控制器
│   │   ├── service/               # 服务层
│   │   ├── mapper/                # 数据访问层
│   │   ├── entity/                # 实体类
│   │   ├── dto/                   # 数据传输对象
│   │   ├── handler/               # 类型处理器
│   │   └── common/                # 公共模块
│   └── src/main/resources/
│       ├── application.yml
│       ├── mapper/                # MyBatis XML
│       └── sql/                   # 数据库脚本
├── python-ai/                     # Python AI 层
│   ├── app/
│   │   ├── api/                   # API 路由
│   │   ├── core/
│   │   │   ├── agent/             # Agent 系统 (ReAct、多Agent、审批、Checkpoint)
│   │   │   ├── rag/               # RAG 引擎 (~23 模块)
│   │   │   ├── llm/               # LLM 接口 (DeepSeek/Ollama/Mock/Failover/ModelGateway)
│   │   │   ├── embedding/         # 向量化
│   │   │   ├── vectorstore/       # 向量存储 (Milvus)
│   │   │   ├── tools/             # 工具系统 (7 工具 + MCP)
│   │   │   ├── chunker/           # 语义分块
│   │   │   ├── policy/            # 策略引擎 (护栏、脱敏)
│   │   │   └── parser/            # 文档解析
│   │   ├── models/                # 数据模型
│   │   └── utils/                 # 工具函数
│   └── requirements.txt
├── hfusionhub-frontend/           # 前端界面 (Vue 3 + TypeScript)
│   ├── src/
│   │   ├── pages/                 # 页面组件
│   │   ├── components/            # 公共组件
│   │   ├── api/                   # API 接口
│   │   └── utils/                 # 工具函数
│   └── package.json
└── README.md
```

## 🚀 快速开始

### 方式一：一键启动（推荐，Windows / Linux / macOS）

```bash
# Windows PowerShell
.\scripts\setup.ps1            # 基础设施 + 开发指引（三终端热重载）
.\scripts\setup.ps1 -FullStack # 全部容器化，一条命令启动完整平台

# Linux / macOS
bash scripts/setup.sh          # 基础设施 + 开发指引
bash scripts/setup.sh --fullstack  # 全部容器化
```

脚本会自动：
1. 检查 Docker 等前置依赖；
2. 生成强随机口令并写入 `docker/.env`、`python-ai/.env`、`deploy/.env`（`scripts/init-env.ps1` / `init-env.sh`）；
3. 启动基础设施（MySQL / Redis / MinIO / Plugin Runner）并等待健康；
4. `-FullStack` 模式继续构建/拉取 Java、Python、前端镜像并启动全平台，完成后打印访问地址。

> Runner TLS 证书路径需手动生成：`bash scripts/generate-runner-tls.sh deploy/runner-tls`。
> 管理员账号：`admin` / `ADMIN_PASSWORD`（由 init-env 随机生成并打印，可在 `docker/.env` 中修改）。

### 方式二：手动启动（开发热重载）

#### 环境要求

- Java 17+
- Python 3.11+
- MySQL 8.0 (Docker)
- Redis 7.x (Docker)
- Node.js 20.19+ 或 22.12+（Vite 8 要求）

#### 启动步骤

```bash
# 1. 克隆项目并启动 MySQL、Redis
git clone https://github.com/xiaodu55/HFusionHub.git
cd HFusionHub
# 必须使用自己的随机值；请勿提交 .env 文件
export MYSQL_ROOT_PASSWORD='replace-with-a-strong-password'
export MYSQL_PASSWORD='replace-with-a-strong-password'
export PLUGIN_RUNNER_TOKEN='replace-with-a-long-random-token'
export MINIO_ROOT_USER='minioadmin'
export MINIO_ROOT_PASSWORD='minioadmin'
export DB_PASSWORD="$MYSQL_PASSWORD"
export CALLBACK_SECRET='replace-with-a-long-random-secret'
export PYTHON_AI_INTERNAL_TOKEN='replace-with-a-second-long-random-secret'
export ADMIN_PASSWORD='replace-with-a-strong-admin-password'
cd docker
docker compose up -d
```

数据库启动后，在三个独立终端中分别运行：

```bash
# 终端 1：Java 后端
cd HFusionHub/java-backend
# 若 docker/.env 的 MINIO_ROOT_USER/PASSWORD 非默认值，需显式传给 Java，
# 否则 MinIO 工件存储会被禁用（日志提示签名不匹配）：
export MINIO_ACCESS_KEY="$MINIO_ROOT_USER"
export MINIO_SECRET_KEY="$MINIO_ROOT_PASSWORD"
mvn spring-boot:run
```

```bash
# 终端 2：Python AI 层
cd HFusionHub/python-ai
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

```bash
# 终端 3：前端
cd HFusionHub/hfusionhub-frontend
npm ci
npm run dev
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
| **Attu (Milvus 网页控制台)** | **8000** | **浏览器查看向量数据：http://localhost:8000** |

**启动后访问**：
- 前端：http://localhost:3000
- Java API：http://localhost:8080
- Python AI 健康检查：http://localhost:9000/health（业务接口仅接受 Java 服务携带的内部令牌）
- API 文档：http://localhost:8080/api/doc.html（Knife4j / Swagger UI）

### 默认账号
- 用户名：admin
- 密码：由 `ADMIN_PASSWORD` 决定

## 🚢 生产部署

### 从预构建镜像部署（推荐）

镜像发布在 GitHub Container Registry（`ghcr.io/xiaodu55/hfusionhub-{java,python,plugin-runner,frontend}`），
打 `v*` tag 时由 CI 自动构建推送。

```bash
cp deploy/.env.example deploy/.env   # 编辑填入密钥；或运行 scripts/init-env.ps1 自动生成
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d
# 访问 http://localhost（前端 :80）
```

### 本地自建镜像部署

```bash
docker compose -f deploy/docker-compose.prod.yml build
docker compose -f deploy/docker-compose.prod.yml up -d
```

> 镜像地址可用 `REGISTRY` / `HFUSIONHUB_TAG` 环境变量覆盖（如内网镜像仓库与指定版本）。
> 生产运维手册见 [docs/PRODUCTION_OPS.md](docs/PRODUCTION_OPS.md)，监控（Prometheus/Grafana）见 `deploy/docker-compose.monitoring.yml`。

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

**RAG 模块：337 个测试用例，100% 通过 | Python AI 总计：1220+ 测试用例 | Java 后端：445 测试用例 | 前端：33 测试用例**

## 🚀 启动指南

详细启动步骤请参阅：
- [docs/startup-guide.md](docs/startup-guide.md) — 中英双语启动、重启和排障指南（原 启动重启1.md 已合并）
- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) — 所有必需环境变量清单
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 架构全景图
- 快速开始：按上方「启动步骤」依次启动 Docker → Java → Python → 前端

## 📚 开发文档

- [Java 后端开发指南](docs/java-backend.md)
- [Python AI 层开发指南](docs/python-ai.md)
- [数据库设计文档](docs/database.md)
- [API 接口文档](docs/api.md)

## 📖 文档索引（Documentation Index）

> 所有文档位于 [docs/](docs/) 目录。按用途分四类：**入口**、**开发**、**运维**、**治理**。
> 2026-08-19 已做文档体系整合：合并 5 份为 3 份权威，删除 1 份冗余，统一关键事实基线
> （Java 445 测试 / Python 1220+ / 前端 33 / Flyway V57 / DeepSeek 已配置）。

### 入口类

| 文档 | 作用 |
|------|------|
| [README.md](README.md) | **本文件**。项目总览、功能模块、快速开始、生产部署、文档索引 |
| [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | AI 编码代理（Claude Code / Codex）的工作指引：架构、命令、数据流、测试、规则（AGENTS 为 CLAUDE 的精简版，二者需保持同步） |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更日志（Keep a Changelog 格式，各轮优化记录） |
| [TODO.md](TODO.md) | 待办操作清单（P0 上线安全 / P1 验证 / P2 生产准备 / P3 优化），含"已自动完成"记录 |

### 开发类

| 文档 | 作用 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **架构全景**（原 ARCHITECTURE + WHITEPAPER 合并）。CQRS 三层架构图、数据流、关键设计决策、安全边界、设计模式、与 Dify/Ragent/LangChain 对比 |
| [docs/java-backend.md](docs/java-backend.md) | Java 后端开发指南：项目结构、设计模式、环境变量、Flyway 规则（V1–V57）、测试与构建 |
| [docs/python-ai.md](docs/python-ai.md) | Python AI 开发指南：模块结构、RAG 管线、Feature Flags、SSE 输出格式、Provider 说明 |
| [docs/database.md](docs/database.md) | 数据库设计：V1–V57 全部迁移历史、核心表、实体关系、迁移规则 |
| [docs/api.md](docs/api.md) | API 接口参考：模块列表、公开端点、调用约定 |
| [docs/agent-v1-scope.md](docs/agent-v1-scope.md) | Agent V1 软件契约：只读研究型 Agent 的能力边界、输入/输出 JSON 契约 |
| [docs/SWAGGER_UI.md](docs/SWAGGER_UI.md) | Swagger UI 配置指南：访问地址、生产关闭/IP 白名单/Basic Auth 策略、注解规范、常见问题 |
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | **环境变量清单（唯一权威）**：Docker/Java/Python 全部变量、Feature Flags（P5 稳定开、实验默认关、冻结保持关） |

### 运维类

| 文档 | 作用 |
|------|------|
| [docs/startup-guide.md](docs/startup-guide.md) | **启动/重启/排障双语指南**（中英对照）：首次安装、一键启动、日常启动顺序、重启决策表、数据库重置、生产部署注意 |
| [docs/PRODUCTION_OPS.md](docs/PRODUCTION_OPS.md) | **生产运维手册**（原 PRODUCTION_OPS + PRODUCTION_CHECKLIST + DR_VECTORS 合并）：上线检查清单、Runner TLS、插件 digest、配额账本、Agent 故障定位、向量库容灾、Staging 演练 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 故障排查手册：P0 服务不可用 / P1 功能异常 / P2 性能 / P3 非关键，含数据恢复与日志收集 |
| [docs/SCALING.md](docs/SCALING.md) | **扩容与性能手册**（原 SCALING + PERFORMANCE_BASELINE 合并）：扩容决策矩阵、垂直/水平扩容、K8s/Helm、性能基线测试、监控告警、成本优化 |
| [docs/PLUGIN_RUNNER_TLS.md](docs/PLUGIN_RUNNER_TLS.md) | Plugin Runner 主机级 Docker daemon TLS 配置指引（当前环境阻塞项） |

### 治理类

| 文档 | 作用 |
|------|------|
| [docs/ROADMAP.md](docs/ROADMAP.md) | **路线图**（原 ROADMAP + PROJECT_ASSESSMENT 合并）：当前状态、Phase 0–6 完成情况、2026-08-18 评估快照存档 |
| [docs/CI_GATES.md](docs/CI_GATES.md) | CI 门禁：Compose 校验、Python/Java/前端测试、离线评测门禁（PR 阻塞）、nightly 运行时评测 |
| [docs/SECURITY_REGRESSION.md](docs/SECURITY_REGRESSION.md) | 安全回归清单：每日/每次发布必查的 5 条安全边界（租户隔离、HMAC 回调、插件沙箱、配额幂等、租户拒绝执行） |

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

## 🤝 贡献

欢迎参与贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

## 📄 许可证

Apache-2.0 许可证。详见 [LICENSE](LICENSE) 文件。
