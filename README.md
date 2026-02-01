# HFusionHub

> Java + Python 混合架构的 AI Agent 智能助手平台

## 🚀 项目简介

HFusionHub 是一个企业级 AI Agent 平台，结合 Java 后端的稳定性和 Python AI 的灵活性，提供完整的 RAG + Agent 解决方案。

### 核心特性

- **Java 后端**：Spring Boot 3.x + MyBatis Plus + MySQL + Redis
- **Python AI 层**：FastAPI + LangChain（可选）+ Milvus
- **Agent 核心**：ReAct 循环、工具调用、会话记忆
- **RAG 引擎**：多路检索、向量召回、语义分块
- **Web 界面**：Vue 3 + Vite 8 + TypeScript + Tailwind CSS 4

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

### 3. 工具系统（Python）
- 知识库检索工具
- 计算器工具
- 天气查询工具
- 自定义工具扩展

### 4. 对话管理（Java + Python）
- 多轮对话
- 会话记忆
- 历史记录
- 上下文管理

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端界面层                              │
│         (Vue 3 + Vite 8 + TypeScript + Tailwind)         │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP/WebSocket
┌─────────────────────▼───────────────────────────────────┐
│                 Java 后端服务层                           │
│            (Spring Boot 3.x + MyBatis Plus)              │
├─────────────────────────────────────────────────────────┤
│  • 用户认证 (JWT + Sa-Token)                             │
│  • 知识库管理 (CRUD、权限)                                │
│  • 对话记录 (MySQL)                                      │
│  • 调用Python AI服务 (HTTP)                              │
│  • 流式输出转发 (SSE)                                     │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP
┌─────────────────────▼───────────────────────────────────┐
│                Python AI Agent 层                        │
│              (FastAPI + LangChain)                       │
├─────────────────────────────────────────────────────────┤
│  • ReAct Agent循环        • 工具调用系统                  │
│  • RAG检索引擎            • 会话记忆管理                  │
│  • 向量数据库 (Milvus)    • 流式输出 (SSE)               │
│  • LLM调用 (Claude)       • 多模型路由                   │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                    数据存储层                             │
├─────────────────────────────────────────────────────────┤
│  • MySQL 8.0 (用户、知识库、对话)                         │
│  • Redis 7.x (缓存、会话、限流)                           │
│  • Milvus 2.x (向量存储)                                 │
│  • MinIO (文件存储)                                      │
└─────────────────────────────────────────────────────────┘
```

## 📁 项目结构

```
HFusionHub/
├── docs/                          # 项目文档
├── java-backend/                  # Java 后端
│   ├── src/
│   │   ├── main/
│   │   │   ├── java/
│   │   │   │   └── com/hfusionhub/
│   │   │   │       ├── config/    # 配置类
│   │   │   │       ├── controller/ # 控制器
│   │   │   │       ├── service/   # 服务层
│   │   │   │       ├── mapper/    # 数据访问层
│   │   │   │       ├── entity/    # 实体类
│   │   │   │       ├── dto/       # 数据传输对象
│   │   │   │       └── common/    # 公共模块
│   │   │   └── resources/
│   │   │       ├── application.yml
│   │   │       └── mapper/        # MyBatis XML
│   │   └── test/
│   └── pom.xml
├── python-ai/                     # Python AI 层
│   ├── app/
│   │   ├── api/                   # API 路由
│   │   ├── core/                  # 核心模块
│   │   │   ├── agent/             # Agent 循环
│   │   │   ├── rag/               # RAG 引擎
│   │   │   ├── tools/             # 工具系统
│   │   │   └── memory/            # 会话记忆
│   │   ├── models/                # 数据模型
│   │   └── utils/                 # 工具函数
│   ├── requirements.txt
│   └── main.py
├── hfusionhub-frontend/           # 前端界面 (Vue 3 + TypeScript)
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── docker/                        # Docker 配置
├── scripts/                       # 脚本工具
└── README.md
```

## 🚀 快速开始

### 环境要求

- Java 17+
- Python 3.10+
- MySQL 8.0
- Redis 7.x
- Milvus 2.x
- Node.js 18+（前端）

### 启动步骤

```bash
# 1. 克隆项目
git clone https://github.com/your-username/HFusionHub.git
cd HFusionHub

# 2. 启动数据库
docker-compose up -d mysql redis milvus

# 3. 启动 Java 后端
cd java-backend
mvn spring-boot:run

# 4. 启动 Python AI 层
cd python-ai
pip install -r requirements.txt
python main.py

# 5. 启动前端
cd hfusionhub-frontend
npm install
npm run dev
```

## 📚 开发文档

- [Java 后端开发指南](docs/java-backend.md)
- [Python AI 层开发指南](docs/python-ai.md)
- [数据库设计文档](docs/database.md)
- [API 接口文档](docs/api.md)

## 🤝 贡献

欢迎参与贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

## 📄 许可证

本项目基于 [Apache-2.0](LICENSE) 许可证开源。
