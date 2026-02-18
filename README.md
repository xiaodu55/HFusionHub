# HFusionHub

> Java + Python 混合架构的 AI Agent 智能助手平台

## 🚀 项目简介

HFusionHub 是一个企业级 AI Agent 平台，结合 Java 后端的稳定性和 Python AI 的灵活性，提供完整的 RAG + Agent 解决方案。

### 核心特性

- **Java 后端**：Spring Boot 3.x + MyBatis Plus + MySQL + Redis
- **Python AI 层**：FastAPI + Milvus Lite
- **Agent 核心**：ReAct 循环、工具调用、会话记忆
- **RAG 引擎**：多路检索、向量召回、语义分块、知识来源持久化
- **Web 界面**：Vue 3 + Vite + TypeScript + Tailwind CSS

## 📋 功能模块

### 1. 知识库管理（Java）
- 文档上传（PDF、Word、TXT、Markdown）
- 文档解析（Apache Tika）
- 知识库 CRUD
- 权限管理

### 2. Agent 核心（Python）
- ReAct 循环实现
- 工具注册与管理
- 工具调用执行
- 流式输出（SSE）
- 知识来源持久化

### 3. RAG 引擎（Python）
- 意图识别（IntentClassifier）
- 查询分解（QueryDecomposer）
- 上下文压缩（ContextCompressor）
- 自我反思（SelfReflector）
- 智能检索路由（QueryRouter）
- 多轮检索策略（MultiTurnStrategy）
- 知识图谱（KnowledgeGraph）

### 4. 工具系统（Python）
- 知识库检索工具
- 计算器工具
- 天气查询工具
- 自定义工具扩展

### 5. 对话管理（Java + Python）
- 多轮对话
- 会话记忆
- 历史记录
- 上下文管理
- 知识来源显示

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
│  • 向量数据库 (Milvus Lite) • 流式输出 (SSE)            │
│  • LLM调用 (DeepSeek)     • 多模型路由                   │
│  • 知识来源格式化                                       │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                    数据存储层                             │
├─────────────────────────────────────────────────────────┤
│  • MySQL 8.0 (用户、知识库、对话、知识来源)               │
│  • Redis 7.x (缓存、会话、限流)                           │
│  • Milvus Lite (向量存储，文件模式)                       │
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
│   │   │   ├── agent/             # Agent 循环
│   │   │   ├── rag/               # RAG 引擎 (8个模块)
│   │   │   ├── llm/               # LLM 接口
│   │   │   ├── embedding/         # 向量化
│   │   │   ├── vectorstore/       # 向量存储
│   │   │   ├── tools/             # 工具系统
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
- Python 3.10+
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
export DB_PASSWORD="$MYSQL_ROOT_PASSWORD"
export CALLBACK_SECRET='replace-with-a-long-random-secret'
export PYTHON_AI_INTERNAL_TOKEN='replace-with-a-second-long-random-secret'
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
| 前端 | 3000 | Vite开发服务器 |
| Java 后端 | 8080 | Spring Boot |
| Python AI | 9000 | FastAPI |
| MySQL | 3306 | Docker容器 |
| Redis | 6379 | Docker容器 |

**启动后访问**：
- 前端：http://localhost:3000
- Java API：http://localhost:8080
- Python AI 健康检查：http://localhost:9000/health（业务接口仅接受 Java 服务携带的内部令牌）
- API文档：http://localhost:8080/doc.html

### 默认账号
- 用户名：admin
- 密码：admin123

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

**总计：333个测试用例，100%通过**

## 📚 开发文档

- [Java 后端开发指南](docs/java-backend.md)
- [Python AI 层开发指南](docs/python-ai.md)
- [数据库设计文档](docs/database.md)
- [API 接口文档](docs/api.md)

## 🤝 贡献

欢迎参与贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

## 📄 许可证

本项目基于 [Apache-2.0](LICENSE) 许可证开源。
