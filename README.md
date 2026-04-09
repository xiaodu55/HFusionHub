# HFusionHub

> Java + Python 混合架构的 AI Agent 智能助手平台

## 🚀 项目简介

HFusionHub 是一个企业级 AI Agent 平台，结合 Java 后端的稳定性和 Python AI 的灵活性，提供完整的 RAG + Agent 解决方案。

### 核心特性

- **Java 后端**：Spring Boot 3.x + MyBatis Plus + MySQL + Redis
- **Python AI 层**：FastAPI + Milvus Lite（开发）/ Milvus Standalone（生产）
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
│  • 向量数据库 (Milvus Lite/Standalone) • 流式输出 (SSE)            │
│  • LLM调用 (DeepSeek/Ollama/OpenAI兼容)  • 多模型路由 + 降级      │
│  • 知识来源格式化                                       │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                    数据存储层                             │
├─────────────────────────────────────────────────────────┤
│  • MySQL 8.0 (用户、知识库、对话、知识来源)               │
│  • Redis 7.x (缓存、会话、限流)                           │
│  • Milvus Lite / Standalone (向量存储)                       │
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

### 环境要求

- Java 17+
- Python 3.11+
- MySQL 8.0 (Docker)
- Redis 7.x (Docker)
- Node.js 20.19+ 或 22.12+（Vite 8 要求）

### 启动步骤

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
| Milvus (prod) | 19530 | 向量数据库 |

**启动后访问**：
- 前端：http://localhost:3000
- Java API：http://localhost:8080
- Python AI 健康检查：http://localhost:9000/health（业务接口仅接受 Java 服务携带的内部令牌）
- API 文档：http://localhost:8080/api/doc.html（Knife4j / Swagger UI）

### 默认账号
- 用户名：admin
- 密码：由 `ADMIN_PASSWORD` 决定

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

**RAG 模块：337 个测试用例，100% 通过 | Python AI 总计：1214+ 测试用例 | Java 后端：401 测试用例**

## 🚀 启动指南

详细启动步骤请参阅：
- [docs/启动重启1.md](docs/启动重启1.md) — 中文启动、重启和排障指南
- [docs/startup-guide.md](docs/startup-guide.md) — English startup and restart guide
- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) — 所有必需环境变量清单
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 架构全景图
- 快速开始：按上方「启动步骤」依次启动 Docker → Java → Python → 前端

## 📚 开发文档

- [Java 后端开发指南](docs/java-backend.md)
- [Python AI 层开发指南](docs/python-ai.md)
- [数据库设计文档](docs/database.md)
- [API 接口文档](docs/api.md)

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
