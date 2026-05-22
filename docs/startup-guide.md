# HFusionHub 启动与运维指南 / Startup & Operations Guide

> 本文档合并自原《启动重启1.md》（中文）与《startup-guide.md》（英文），作为首次安装、日常启动、重启与排障的唯一指南。
> This document merges the former Chinese guide (启动重启1.md) and English guide (startup-guide.md) into one bilingual reference for first-time setup, daily startup, restart, and troubleshooting.
>
> 生产部署请同时查看 `deploy/docker-compose.prod.yml` 与 `docs/ENVIRONMENT.md`。
> For production deployment also see `deploy/docker-compose.prod.yml` and `docs/ENVIRONMENT.md`.

---

# Part 1 — 中文指南

## 0. 前置要求

| 依赖 | 版本要求 | 说明 |
| :--- | :--- | :--- |
| Java | 17+ | Spring Boot 3.2 运行环境 |
| Python | 3.11+ | AI 服务运行环境 |
| Node.js | 20.19+ 或 22.12+ | Vite 8 前端开发服务器 |
| Docker | Desktop / Engine | 运行 MySQL、Redis、MinIO、Milvus、Plugin Runner |
| Maven | 3.8+（或使用 `mvnw`） | Java 后端构建 |

---

## 1. 首次安装（刚从仓库拉取）

### 1.1 一键启动（推荐）

项目提供自动初始化脚本：生成强随机密钥、写入 `.env`、启动基础设施并等待健康检查。

```powershell
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
3. 启动基础设施（MySQL / Redis / MinIO / Milvus / Attu / Plugin Runner）并等待健康。

> 手动填写：`DEEPSEEK_API_KEY`（模型供应商控制台获取，当前开发环境已配置真实 key）与 Runner TLS 证书路径（`bash scripts/generate-runner-tls.sh deploy/runner-tls`）。
> 管理员账号：`admin` / `ADMIN_PASSWORD`（由 init-env 随机生成并打印，可在 `docker/.env` 中修改）。

以下 1.2–1.8 为**手动方式**（备选，适用于需要逐项控制的场景）。

### 1.2 克隆项目与创建环境变量文件

```bash
git clone https://github.com/xiaodu55/HFusionHub.git
cd HFusionHub
```

项目使用 `.env` 文件管理密钥，这些文件**不提交到 Git**。需要从示例模板复制：

```powershell
# 在项目根目录下执行

# 1) Docker 基础设施的 .env
copy docker\.env.example docker\.env

# 2) Python AI 的 .env
copy python-ai\.env.example python-ai\.env
```

### 1.3 填写必需的密钥和配置

编辑 `docker\.env`，使用你自己的随机值替换：

```ini
# docker\.env — 必需项
MYSQL_ROOT_PASSWORD=替换为强密码
MYSQL_PASSWORD=替换为数据库用户密码
ADMIN_PASSWORD=替换为管理员初始密码
PLUGIN_RUNNER_TOKEN=替换为 Runner 令牌（必填 — 缺少则 docker compose up 失败）

# 以下可保留默认值
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

编辑 `python-ai\.env`，至少配置 LLM：

```ini
# python-ai\.env — 必需项
DEEPSEEK_API_KEY=你的DeepSeek_API_Key

# 如果使用 Ollama 做 embedding（推荐），还需配置：
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=bge-m3:latest
# 注意：变量名是 OLLAMA_EMBEDDING_MODEL，不要用旧的 OLLAMA_MODEL（已废弃）

# 向量库默认连接 Docker 中的 Milvus Standalone（cluster 模式）：
VECTOR_STORE_MODE=cluster
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530

# 其余可保留 .env.example 的默认值
```

> **安全提示**：不要使用示例中的密码。不要将 `.env` 文件提交到 Git（已在 `.gitignore` 中忽略）。

### 1.4 设置会话环境变量

在启动 Java 和 Python 的终端中，需要设置与 `docker/.env` 一致的环境变量：

```powershell
# ===== 每次启动都需要设置的环境变量 =====
# 数据库
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD="<与 docker\.env 中 MYSQL_PASSWORD 相同>"

# Redis（docker\.env 中 REDIS_PASSWORD 设了密码则必须注入，否则 Java 报 NOAUTH）
$env:REDIS_PASSWORD="<与 docker\.env 中 REDIS_PASSWORD 相同>"

# Java ↔ Python 互信令牌（自行生成随机值，两端必须一致）
$env:CALLBACK_SECRET="<生成一个长随机字符串>"
$env:PYTHON_AI_INTERNAL_TOKEN="<生成另一个长随机字符串>"

# 管理员初始密码
$env:ADMIN_PASSWORD="<与 docker\.env 中 ADMIN_PASSWORD 相同>"

# Python LLM
$env:DEEPSEEK_API_KEY="<你的 DeepSeek API Key>"
```

> 生成随机字符串可以用：`node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"` 或 `openssl rand -hex 32`。
> 也可以直接用 `scripts/init-env.ps1` / `init-env.sh` 自动生成并写入三个 `.env` 文件，再按需修改。

### 1.5 启动 Docker 基础设施

```powershell
cd docker
docker compose up -d
```

等待所有容器健康检查通过：

```powershell
docker compose ps
# 确认 mysql8、redis7、minio、milvus、etcd、attu、plugin-runner 等容器的 STATUS 都是 healthy（或 running）
```

**Docker 服务一览**：

| 服务 | 端口 | 用途 |
| :--- | :--- | :--- |
| MySQL 8.0 | `127.0.0.1:3306` | 业务数据库 |
| Redis 7 | `127.0.0.1:6379` | 缓存与会话 |
| MinIO | `127.0.0.1:9002`（API）、`9001`（控制台） | 文件对象存储 |
| Milvus Standalone | `127.0.0.1:19530`（gRPC）、`9091`（HTTP） | 向量数据库 |
| Attu（Milvus 网页控制台） | `127.0.0.1:8000` | 浏览器查看向量数据 |
| Plugin Runner | `127.0.0.1:9100` | 插件沙箱执行 |

### 1.6 启动 Java 后端（首次会执行数据库迁移）

```powershell
cd ..\java-backend

# 确保环境变量已设置（见 1.4 节）
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD="<MYSQL_PASSWORD>"
$env:CALLBACK_SECRET="<你的回调密钥>"
$env:PYTHON_AI_INTERNAL_TOKEN="<你的内部令牌>"
$env:ADMIN_PASSWORD="<管理员密码>"

# 编译并启动（首次会下载依赖，需要几分钟）
mvn spring-boot:run
```

首次启动时 Flyway 会自动执行 `V1` ~ `V57+` 数据库迁移脚本，创建所有表结构。

验证：

```powershell
# 健康检查
Invoke-WebRequest http://localhost:8080/api/actuator/health

# API 文档
# 浏览器打开: http://localhost:8080/api/doc.html
```

### 1.7 启动 Python AI 服务

```powershell
cd ..\python-ai

# 创建虚拟环境（仅首次需要）
python -m venv .venv

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # macOS / Linux / Git Bash

# 安装依赖（首次需要几分钟）
pip install -r requirements.txt

# 确保环境变量已设置
$env:PYTHON_AI_INTERNAL_TOKEN="<与 Java 端相同>"
$env:CALLBACK_SECRET="<与 Java 端相同>"
$env:DEEPSEEK_API_KEY="<你的 DeepSeek API Key>"
$env:JAVA_BACKEND_URL="http://localhost:8080"

# 启动
python -m app.main
```

验证：

```powershell
# 健康检查
Invoke-WebRequest http://localhost:9000/health
# 应返回 {"status": "healthy"}
```

> **注意**：
> - `DEEPSEEK_API_KEY` 用于聊天 LLM。文档向量化（embedding）需要额外的 embedding 服务（Ollama 等）。
> - 本地开发测试可以设置 `$env:EMBEDDING_ALLOW_FALLBACK="true"` 启用随机向量降级（**仅限本地测试，生产禁止**）。
> - 如果 Python 返回 401/403，检查 `PYTHON_AI_INTERNAL_TOKEN` 两端是否一致。

### 1.8 启动前端

```powershell
cd ..\hfusionhub-frontend

# 安装依赖（仅首次需要）
npm ci

# 启动开发服务器
npm run dev
```

验证：浏览器打开 `http://localhost:3000`。

Vite 开发服务器会自动将 `/api` 请求代理到 `http://localhost:8080`（Java 后端）。

### 1.9 首次安装完成 — 验证清单

| 服务 | 地址 | 验证方式 |
| :--- | :--- | :--- |
| 前端 | http://localhost:3000 | 浏览器打开，能看到登录页面 |
| Java API | http://localhost:8080/api | `Invoke-WebRequest http://localhost:8080/api/actuator/health` |
| API 文档 | http://localhost:8080/api/doc.html | 浏览器打开 Knife4j / Swagger UI |
| Python AI | http://localhost:9000/health | 返回 `{"status": "healthy"}` |
| Python API 文档 | http://localhost:9000/docs | 浏览器打开 FastAPI Swagger UI（或 /redoc） |
| MySQL | `localhost:3306` | `docker compose ps`（docker 目录下），状态 healthy |
| Redis | `localhost:6379` | `docker compose ps`，状态 healthy |
| MinIO 控制台 | http://localhost:9001 | 浏览器打开，用 `docker/.env` 中配置的凭证登录 |
| Milvus | http://localhost:9091/healthz | `curl http://localhost:9091/healthz` 返回 OK |
| Attu（向量数据控制台） | http://localhost:8000 | 浏览器打开，连接地址填 `127.0.0.1:19530` |
| Plugin Runner | http://localhost:9100/health | `Invoke-WebRequest http://localhost:9100/health` |

**默认登录**：
- 用户名：`admin`
- 密码：你在 `ADMIN_PASSWORD` 中设置的值

**首次登录后建议操作**：

1. **导入演示数据**（可选）：访问 `设置` 页面，点击「导入演示数据」按钮，一键生成演示知识库、文档、回答方案、笔记、记忆、应用和公告，帮助快速了解平台功能。

2. **配置主题偏好**：在 `设置` 页面选择 `浅色`/`深色`/`跟随系统` 三档主题，偏好会同步到服务端，换设备登录时自动应用。

3. **查看配额状态**：访问 `用量与费用` 页面，查看当前租户的 Token 配额和存储配额使用情况。当配额用量超过 70% 时会显示告警色，超过 100% 时对话发送按钮会被禁用。

4. **清理演示数据**：测试完成后，可在 `设置` 页面点击「清空演示数据」，删除所有演示内容（保留用户账号和真实数据）。

---

## 2. 日常启动（非首次）

以下假设 Docker 容器已在运行、虚拟环境和依赖已安装。

### 2.1 推荐启动顺序

| 顺序 | 服务 | 命令 |
| :--- | :--- | :--- |
| 1 | Docker 基础设施 | `cd docker && docker compose up -d` |
| 2 | Java + Python 一键 | `powershell -ExecutionPolicy Bypass -File scripts/restart-modules.ps1 -Modules java,python` |
| 3 | 前端 | `cd hfusionhub-frontend && npm run dev` |

> **推荐用 `restart-modules.ps1` 一键启动 Java/Python**，它自动：
> 1. 读取 `docker\.env` 并注入 `DB_PASSWORD`/`REDIS_PASSWORD`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` 等变量（无需手动 export）；
> 2. 启动后轮询健康检查，非 healthy 会退出非零；
> 3. 日志落盘到模块目录下的 `<module>-live.log` / `<module>-live-err.log`（如 `java-backend/java-live.log`），方便排障。
>
> ⚠️ 注意：`-Modules java,python` 的逗号写法在 PowerShell 5.1 的 `-File` 模式下会被绑定成单个字符串，脚本内部已做归一化处理（2026-08-21 修复）；`runner` 由 docker compose 容器管理，重启 runner 请用 `docker compose restart plugin-runner`。
>
> 也可以手动逐个启动（见 2.2–2.4），或仅热重启某个模块：`.\scripts\restart-modules.ps1 -Modules python`。

### 2.2 Java 后端（快速启动）

```powershell
cd java-backend
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD="<与 MYSQL_PASSWORD 相同>"
$env:REDIS_PASSWORD="<与 REDIS_PASSWORD 相同，Redis 设了密码则必填，否则 NOAUTH>"
$env:CALLBACK_SECRET="<与 Python 相同>"
$env:PYTHON_AI_INTERNAL_TOKEN="<与 Python 相同>"
$env:ADMIN_PASSWORD="<管理员初始化密码>"
# 若 docker/.env 的 MINIO_ROOT_USER/PASSWORD 非默认值（minioadmin），必须传给 Java，
# 否则日志提示 "MinIO not available, artifact storage disabled"（插件工件存储被禁用）：
$env:MINIO_ACCESS_KEY="<MINIO_ROOT_USER 值>"
$env:MINIO_SECRET_KEY="<MINIO_ROOT_PASSWORD 值>"
mvn spring-boot:run
```

### 2.3 Python AI 服务（快速启动）

```powershell
cd python-ai
.\.venv\Scripts\Activate.ps1
$env:PYTHON_AI_INTERNAL_TOKEN="<与 Java 相同>"
$env:CALLBACK_SECRET="<与 Java 相同>"
$env:DEEPSEEK_API_KEY="<DeepSeek API Key>"
$env:JAVA_BACKEND_URL="http://localhost:8080"
python -m app.main
```

### 2.4 前端（快速启动）

```powershell
cd hfusionhub-frontend
npm run dev
```

---

## 3. 重启指南

| 变更内容 | 需要重启的服务 |
| :--- | :--- |
| 数据库 / Redis / 认证 / 回调 / AI 服务地址 | Java |
| LLM / embedding / RAG / 内部令牌 / 回调 | Python |
| Vite 配置 / 前端依赖 | 前端 |
| MySQL / Redis / Milvus 配置 | Docker 基础设施 |

---

## 4. 本地重置数据库

以下命令会**删除**本地 MySQL 数据卷，所有数据将丢失：

```powershell
cd docker
docker compose down -v
docker compose up -d
```

重置后重新启动 Java，Flyway 会按 `V1` ~ `V57+` 自动重建 schema。

> ⚠️ 以后新增表结构必须创建新的 `V58+` 迁移文件，**不要修改已有的迁移文件**，否则会导致 Flyway checksum mismatch。
> 提示：`down -v` 也会删除 Milvus 向量卷（`<project>_milvus-data`）；如需保留向量数据，改用 `docker compose down`（不带 `-v`），或先执行 `scripts/backup_milvus.sh`。

---

## 5. 生产部署注意事项

`deploy/docker-compose.prod.yml` 已经配置了容器内服务地址：

- `SPRING_DATASOURCE_URL=jdbc:mysql://mysql8:3306/hfusionhub?...`
- `SPRING_DATA_REDIS_HOST=redis7`
- `AI_SERVICE_URL=http://python-ai:9000`
- `PYTHON_AI_CALLBACK_BASE_URL=http://java-backend:8080/api`
- `LLM_ALLOW_MOCK=false`
- `EMBEDDING_ALLOW_FALLBACK=false`

生产栈包含 Milvus Standalone（外部 etcd）+ Attu，`VECTOR_STORE_MODE=cluster` 已默认。镜像从 GHCR 拉取：

```bash
cp deploy/.env.example deploy/.env   # 或运行 scripts/init-env.ps1 自动生成
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d
```

Helm 模板已包含等价的 Java 环境覆盖项，可直接用于生产部署。详细运维见 `docs/PRODUCTION_OPS.md`。

---

## 6. 常见问题

| 问题 | 原因 | 解决方法 |
| :--- | :--- | :--- |
| Java 调 Python 返回 401/403 | `PYTHON_AI_INTERNAL_TOKEN` 不一致 | 确认 Java 和 Python 两端的环境变量完全相同 |
| Python 回调 Java 失败 | `CALLBACK_SECRET` 不一致或网络不通 | 确认两端 `CALLBACK_SECRET` 一致，且 Python 能访问 Java |
| 文档向量化失败 | 无 embedding 服务 | 配置 Ollama (`OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL`)；或临时设置 `EMBEDDING_ALLOW_FALLBACK=true` |
| Milvus 连接失败 | cluster 模式下 Milvus 容器未启动 | `cd docker && docker compose up -d`，确认 `docker compose ps` 中 milvus/etcd 为 healthy；`VECTOR_STORE_MODE=lite` 为本地裸跑可选模式 |
| Attu 提示 "No connection established" | 浏览器连不上 Milvus 地址 | 连接地址填 `127.0.0.1:19530`（浏览器解析 `localhost` 可能走 IPv6 导致失败） |
| Flyway checksum mismatch | 已有迁移文件被修改 | 本地开发可用第 4 节重置数据库；生产环境创建新的迁移脚本 |
| 数据库连接失败 | `DB_PASSWORD` 与 `MYSQL_PASSWORD` 不匹配 | 确保 Java 终端的 `DB_PASSWORD` 与 `docker/.env` 中的 `MYSQL_PASSWORD` 一致 |
| 前端 `npm ci` 失败 | Node.js 版本不满足 | 使用 `nvm` 切换至 Node.js 20.19+ 或 22.12+ |
| Docker 容器未全部 healthy | 启动顺序或资源不足 | 等待 30 秒后 `docker compose ps` 检查；必要时 `docker compose restart` |
| `.env` 文件未找到 | 首次克隆后未创建 | 执行 `copy docker\.env.example docker\.env` 和 `copy python-ai\.env.example python-ai\.env`，或直接运行 `scripts/init-env.ps1` |
| Java 调 Python 报 `400 Invalid HTTP request received.` | **JDK HttpClient 默认 HTTP/2**，对明文 `http://` 发 `Upgrade: h2c` 探测，uvicorn/h11 不支持 | 已修复（[RestTemplateConfig.java](../java-backend/src/main/java/com/hfusionhub/config/RestTemplateConfig.java) 显式 `.version(HTTP_1_1)`）。若升级依赖后复现，确认 RestTemplate 底层仍是 JDK HttpClient 且锁定 HTTP/1.1 |
| `restart-modules.ps1` 报 healthy 但服务没起来 | PowerShell 5.1 `-File` 模式下 `-Modules java,python` 被绑定成单个字符串，ContainsKey 全 miss | 已修复（脚本内 `-split ','` 归一化）。升级到新版脚本后重试；若自定义脚本，注意 `-Command` 才拆逗号 |
| 检索到 0 条来源（Retrieved 0 sources） | 向量库（Milvus）或本地源文件被清空，MySQL 元数据残留 | 见下方「RAG 空库恢复」 |

---

### 6.1 RAG 空库恢复

**症状**：聊天检索返回 0 条来源，但知识库显示文档状态 COMPLETED。

**判断**：Milvus 集合 `hfusionhub_chunks` 实体数为 0（`num_entities=0`）但 MySQL `document_chunk` 有数据，说明向量库被清空（容器重建/卷漂移），源文件也可能已丢失。

**恢复流程**：

1. 检查向量库：Attu（http://localhost:8000）查看 `hfusionhub_chunks` 集合，或 Python 直接查询：
   ```python
   from pymilvus import connections, utility
   connections.connect(alias="default", host="127.0.0.1", port="19530")
   print(utility.get_collection_stats("hfusionhub_chunks"))
   ```
2. 源文件缺失时重新上传：`POST /api/document/upload`（multipart），然后触发 `POST /api/vectorize/{id}` 重新解析/向量化。
3. 失效文档先软删（`DELETE /api/document/{id}`，进回收站可恢复）再 `purge`（物理删除，不可逆，会被权限校验拦截）。
4. 参考 [docs/ACCESS_MAP.md](ACCESS_MAP.md) 访问地图定位各服务。

---

## 7. 参考文档

- [docs/ACCESS_MAP.md](ACCESS_MAP.md) — 已启动服务全量访问地图（网址/账号/API 文档/接口清单）
- [docs/ENVIRONMENT.md](ENVIRONMENT.md) — 所有环境变量与特性开关详细说明
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — 架构全景图
- [docs/java-backend.md](java-backend.md) — Java 后端开发指南
- [docs/python-ai.md](python-ai.md) — Python AI 开发指南
- [docs/PRODUCTION_OPS.md](PRODUCTION_OPS.md) — 生产运维指南

---

# Part 2 — English Guide

## 0. Prerequisites

| Dependency | Version | Notes |
| :--- | :--- | :--- |
| Java | 17+ | Spring Boot 3.2 runtime |
| Python | 3.11+ | AI service runtime |
| Node.js | 20.19+ or 22.12+ | Vite 8 dev server |
| Docker | Desktop / Engine | MySQL, Redis, MinIO, Milvus, Plugin Runner |
| Maven | 3.8+ (or use `mvnw`) | Java backend build |

---

## 1. First-Time Setup (Fresh Clone)

### 1.1 One-Command Setup (Recommended)

Automated scripts generate random secrets, write the `.env` files, start the infrastructure, and wait for health checks:

```powershell
# Windows PowerShell
.\scripts\setup.ps1            # Infrastructure + dev guidance (3-terminal hot reload)
.\scripts\setup.ps1 -FullStack # Everything containerized; full platform in one command

# Linux / macOS
bash scripts/setup.sh          # Infrastructure + dev guidance
bash scripts/setup.sh --fullstack  # Fully containerized
```

The scripts will:
1. Check prerequisites such as Docker;
2. Generate strong random secrets into `docker/.env`, `python-ai/.env`, `deploy/.env` (`scripts/init-env.ps1` / `init-env.sh`);
3. Start infrastructure (MySQL / Redis / MinIO / Milvus / Attu / Plugin Runner) and wait until healthy.

> Fill in: `DEEPSEEK_API_KEY` (from your model provider console; the current dev environment already has a real key) and the Runner TLS cert path (`bash scripts/generate-runner-tls.sh deploy/runner-tls`).
> Admin account: `admin` / `ADMIN_PASSWORD` (randomly generated by init-env and printed; editable in `docker/.env`).

Sections 1.2–1.8 below describe the **manual** path (fallback when you need fine-grained control).

### 1.2 Clone & Create Environment Files

```bash
git clone https://github.com/xiaodu55/HFusionHub.git
cd HFusionHub
```

The project manages secrets with `.env` files that are **not committed to Git**. Copy from the example templates:

```powershell
# From the project root:

# 1) Docker infrastructure .env
copy docker\.env.example docker\.env

# 2) Python AI .env
copy python-ai\.env.example python-ai\.env
```

### 1.3 Fill in Required Secrets

Edit `docker\.env` with your own random values:

```ini
# docker\.env — required
MYSQL_ROOT_PASSWORD=replace-with-strong-password
MYSQL_PASSWORD=replace-with-db-user-password
ADMIN_PASSWORD=replace-with-admin-initial-password
PLUGIN_RUNNER_TOKEN=replace-with-runner-token

# Optional — keep defaults for local dev
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

Edit `python-ai\.env` — at minimum configure the LLM:

```ini
# python-ai\.env — required
DEEPSEEK_API_KEY=your-deepseek-api-key

# If using Ollama for embeddings (recommended):
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=bge-m3:latest
# Note: the variable is OLLAMA_EMBEDDING_MODEL, not the deprecated OLLAMA_MODEL

# Vector store connects to the Dockerized Milvus Standalone (cluster mode) by default:
VECTOR_STORE_MODE=cluster
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530

# The rest can keep the defaults from .env.example
```

> **Security**: Never use the example passwords. Never commit `.env` files to Git (already in `.gitignore`).

### 1.4 Set Session Environment Variables

In each terminal that runs Java or Python, set these variables (must match `docker/.env`):

```powershell
# ===== Set in every terminal session =====
# Database
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD="<same as MYSQL_PASSWORD in docker/.env>"

# Java ↔ Python mutual trust tokens (generate your own; must match on both sides)
$env:CALLBACK_SECRET="<generate a long random string>"
$env:PYTHON_AI_INTERNAL_TOKEN="<generate another long random string>"

# Admin initial password
$env:ADMIN_PASSWORD="<same as ADMIN_PASSWORD in docker/.env>"

# Python LLM
$env:DEEPSEEK_API_KEY="<your DeepSeek API Key>"
```

> Generate random strings: `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"` or `openssl rand -hex 32`.
> Alternatively run `scripts/init-env.ps1` / `init-env.sh` to generate and write all three `.env` files automatically, then edit as needed.

### 1.5 Start Docker Infrastructure

```powershell
cd docker
docker compose up -d
```

Wait for all containers to be healthy:

```powershell
docker compose ps
# mysql8, redis7, minio, milvus, etcd, attu, plugin-runner should all be healthy/running
```

**Docker services**:

| Service | Port | Purpose |
| :--- | :--- | :--- |
| MySQL 8.0 | `127.0.0.1:3306` | Business database |
| Redis 7 | `127.0.0.1:6379` | Cache & sessions |
| MinIO | `127.0.0.1:9002` (API), `9001` (Console) | Object storage |
| Milvus Standalone | `127.0.0.1:19530` (gRPC), `9091` (HTTP) | Vector database |
| Attu (Milvus web console) | `127.0.0.1:8000` | Browse vector data in browser |
| Plugin Runner | `127.0.0.1:9100` | Plugin sandbox execution |

### 1.6 Start Java Backend (runs DB migrations on first launch)

```powershell
cd ..\java-backend

# Ensure env vars are set (see §1.4)
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD="<MYSQL_PASSWORD>"
$env:CALLBACK_SECRET="<your callback secret>"
$env:PYTHON_AI_INTERNAL_TOKEN="<your internal token>"
$env:ADMIN_PASSWORD="<admin password>"

# Build & run (first time downloads dependencies; takes a few minutes)
mvn spring-boot:run
```

On first launch, Flyway automatically runs `V1`–`V57+` migration scripts to create all tables.

Verify:

```powershell
# Health check
Invoke-WebRequest http://localhost:8080/api/actuator/health

# API docs
# Open in browser: http://localhost:8080/api/doc.html
```

### 1.7 Start Python AI Service

```powershell
cd ..\python-ai

# Create virtual environment (first time only)
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # macOS / Linux / Git Bash

# Install dependencies (first time; takes a few minutes)
pip install -r requirements.txt

# Ensure env vars are set
$env:PYTHON_AI_INTERNAL_TOKEN="<same as Java side>"
$env:CALLBACK_SECRET="<same as Java side>"
$env:DEEPSEEK_API_KEY="<your DeepSeek API Key>"
$env:JAVA_BACKEND_URL="http://localhost:8080"

# Start
python -m app.main
```

Verify:

```powershell
Invoke-WebRequest http://localhost:9000/health
# Should return {"status": "healthy"}
```

> **Notes**:
> - `DEEPSEEK_API_KEY` is used for chat LLM. Document embedding requires a separate embedding service (Ollama, etc.).
> - For local dev/testing only, set `$env:EMBEDDING_ALLOW_FALLBACK="true"` to enable random-vector fallback (**never in production**).
> - If Python returns 401/403, verify `PYTHON_AI_INTERNAL_TOKEN` matches on both sides.

### 1.8 Start Frontend

```powershell
cd ..\hfusionhub-frontend

# Install dependencies (first time only)
npm ci

# Start dev server
npm run dev
```

Verify: Open `http://localhost:3000` in your browser.

The Vite dev server automatically proxies `/api` requests to `http://localhost:8080` (Java backend).

### 1.9 First-Time Setup Complete — Verification Checklist

| Service | URL | How to Verify |
| :--- | :--- | :--- |
| Frontend | http://localhost:3000 | Open in browser — login page should appear |
| Java API | http://localhost:8080/api | `Invoke-WebRequest http://localhost:8080/api/actuator/health` |
| API Docs | http://localhost:8080/api/doc.html | Open Knife4j / Swagger UI in browser |
| Python AI | http://localhost:9000/health | Returns `{"status": "healthy"}` |
| Python API Docs | http://localhost:9000/docs | Open FastAPI Swagger UI in browser (or /redoc) |
| MySQL | `localhost:3306` | `docker compose ps` (in `docker/` directory), status healthy |
| Redis | `localhost:6379` | `docker compose ps`, status healthy |
| MinIO Console | http://localhost:9001 | Open in browser, log in with credentials from `docker/.env` |
| Milvus | http://localhost:9091/healthz | `curl http://localhost:9091/healthz` returns OK |
| Attu (vector data console) | http://localhost:8000 | Open in browser, connect to `127.0.0.1:19530` |
| Plugin Runner | http://localhost:9100/health | `Invoke-WebRequest http://localhost:9100/health` |

**Default login**:
- Username: `admin`
- Password: the value you set in `ADMIN_PASSWORD`

---

## 2. Daily Startup (After First-Time Setup)

Assumes Docker containers are running and virtual environment/dependencies are already installed.

### 2.1 Recommended Startup Order

| Order | Service | Command |
| :--- | :--- | :--- |
| 1 | Docker infra | `cd docker && docker compose up -d` |
| 2 | Java + Python (one command) | `powershell -ExecutionPolicy Bypass -File scripts/restart-modules.ps1 -Modules java,python` |
| 3 | Frontend | `cd hfusionhub-frontend && npm run dev` |

> **Recommended: use `restart-modules.ps1` to start Java/Python in one shot.** It:
> 1. Loads `docker\.env` and injects `DB_PASSWORD`/`REDIS_PASSWORD`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` etc. (no manual `export` needed);
> 2. Polls health endpoints and exits non-zero if a module never becomes healthy;
> 3. Redirects stdout/stderr to `<module>-live.log` / `<module>-live-err.log` in each module dir (e.g. `java-backend/java-live.log`) for easy debugging.
>
> ⚠️ The comma syntax `-Modules java,python` is bound as a SINGLE string under PowerShell 5.1 `-File` mode (only `-Command` splits on commas); the script normalizes with `-split ','` internally (fixed 2026-08-21). `runner` is managed by the docker compose container — restart it with `docker compose restart plugin-runner`.
>
> You may also start modules individually (see §2.2–2.4) or hot-restart a single module: `.\scripts\restart-modules.ps1 -Modules python`.

### 2.2 Java Backend (Quick Start)

```powershell
cd java-backend
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD="<same as MYSQL_PASSWORD>"
$env:CALLBACK_SECRET="<same secret used by Python>"
$env:PYTHON_AI_INTERNAL_TOKEN="<same token used by Python>"
$env:ADMIN_PASSWORD="<admin bootstrap password>"
# If MINIO_ROOT_USER/PASSWORD in docker/.env are not the defaults (minioadmin),
# pass them explicitly, otherwise Java disables MinIO artifact storage:
$env:MINIO_ACCESS_KEY="<value of MINIO_ROOT_USER>"
$env:MINIO_SECRET_KEY="<value of MINIO_ROOT_PASSWORD>"
mvn spring-boot:run
```

### 2.3 Python AI Service (Quick Start)

```powershell
cd python-ai
.\.venv\Scripts\Activate.ps1
$env:PYTHON_AI_INTERNAL_TOKEN="<same token used by Java>"
$env:CALLBACK_SECRET="<same secret used by Java>"
$env:DEEPSEEK_API_KEY="<deepseek-api-key>"
$env:JAVA_BACKEND_URL="http://localhost:8080"
python -m app.main
```

### 2.4 Frontend (Quick Start)

```powershell
cd hfusionhub-frontend
npm run dev
```

---

## 3. Restart Guide

| Change | Services to Restart |
| :--- | :--- |
| Database / Redis / auth / callback / AI service URL | Java |
| LLM / embedding / RAG / internal token / callback | Python |
| Vite config / frontend dependencies | Frontend |
| MySQL / Redis / Milvus config only | Docker infrastructure |

---

## 4. Local Database Reset

This **deletes** local MySQL data — all data will be lost:

```powershell
cd docker
docker compose down -v
docker compose up -d
```

After reset, restart Java so Flyway can recreate the schema (`V1`–`V57+`).

> ⚠️ For future schema changes, create new `V58+` migration files. **Do not modify existing migrations**, or Flyway will report a checksum mismatch.
> Note: `down -v` also deletes the Milvus vector volume (`<project>_milvus-data`). To keep vector data, use `docker compose down` (without `-v`), or run `scripts/backup_milvus.sh` first.

---

## 5. Production Notes

`deploy/docker-compose.prod.yml` already sets container service URLs:

- `SPRING_DATASOURCE_URL=jdbc:mysql://mysql8:3306/hfusionhub?...`
- `SPRING_DATA_REDIS_HOST=redis7`
- `AI_SERVICE_URL=http://python-ai:9000`
- `PYTHON_AI_CALLBACK_BASE_URL=http://java-backend:8080/api`
- `LLM_ALLOW_MOCK=false`
- `EMBEDDING_ALLOW_FALLBACK=false`

The production stack includes Milvus Standalone (external etcd) + Attu with `VECTOR_STORE_MODE=cluster` by default. Images are pulled from GHCR:

```bash
cp deploy/.env.example deploy/.env   # or run scripts/init-env.ps1 to generate
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d
```

The Helm template already includes equivalent Java environment overrides and is production-ready. See `docs/PRODUCTION_OPS.md` for operations.

---

## 6. Common Issues

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| Java → Python returns 401/403 | `PYTHON_AI_INTERNAL_TOKEN` mismatch | Verify the token is identical in both terminals |
| Python → Java callback fails | `CALLBACK_SECRET` mismatch or network issue | Verify `CALLBACK_SECRET` matches and Python can reach Java |
| Document indexing fails | No embedding service available | Configure Ollama (`OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL`); or temporarily set `EMBEDDING_ALLOW_FALLBACK=true` |
| Milvus connection fails | Milvus container not running in cluster mode | `cd docker && docker compose up -d`; confirm milvus/etcd are healthy in `docker compose ps`. `VECTOR_STORE_MODE=lite` is only for bare-metal local runs |
| Attu "No connection established" | Browser cannot reach Milvus address | Use `127.0.0.1:19530` as the connection address (`localhost` may resolve to IPv6 `::1`) |
| Flyway checksum mismatch | Existing migration files were modified | For local dev, use §4 to reset DB; in production, create a new migration script |
| Database connection failed | `DB_PASSWORD` doesn't match `MYSQL_PASSWORD` | Ensure Java's `DB_PASSWORD` matches `docker/.env`'s `MYSQL_PASSWORD` |
| `npm ci` fails | Node.js version too old/new | Use `nvm` to switch to Node.js 20.19+ or 22.12+ |
| Docker containers not all healthy | Startup order or resource contention | Wait 30s and `docker compose ps`; `docker compose restart` if needed |
| `.env` file not found | Not created after fresh clone | Run `copy docker\.env.example docker\.env` and `copy python-ai\.env.example python-ai\.env`, or run `scripts/init-env.ps1` |
| Java → Python returns `400 Invalid HTTP request received.` | **JDK HttpClient defaults to HTTP/2**, sending an `Upgrade: h2c` probe on plaintext `http://`; uvicorn/h11 rejects h2c | Fixed in [RestTemplateConfig.java](../java-backend/src/main/java/com/hfusionhub/config/RestTemplateConfig.java) by forcing `.version(HTTP_1_1)`. If it recurs after a dependency upgrade, confirm the RestTemplate still uses a JDK HttpClient locked to HTTP/1.1 |
| `restart-modules.ps1` reports healthy but nothing started | PowerShell 5.1 `-File` binds `-Modules java,python` as a single string (only `-Command` splits on commas) so all `ContainsKey` checks miss | Fixed via `-split ','` normalization inside the script. Upgrade to the new script and retry |
| 0 sources retrieved | Vector store (Milvus) or local source files were wiped, leaving stale MySQL metadata | See "RAG empty-store recovery" below |

---

### 6.1 RAG Empty-Store Recovery

**Symptom**: Chat retrieval returns 0 sources, but knowledge-base documents show status COMPLETED.

**Diagnosis**: Milvus collection `hfusionhub_chunks` has 0 entities (`num_entities=0`) while MySQL `document_chunk` still has rows — the vector store was wiped (container rebuild/volume drift) and source files may also be gone.

**Recovery**:

1. Inspect the vector store via Attu (http://localhost:8000) or query directly:
   ```python
   from pymilvus import connections, utility
   connections.connect(alias="default", host="127.0.0.1", port="19530")
   print(utility.get_collection_stats("hfusionhub_chunks"))
   ```
2. If source files are gone, re-upload via `POST /api/document/upload` (multipart), then trigger `POST /api/vectorize/{id}` to re-parse/embed.
3. Soft-delete broken docs first (`DELETE /api/document/{id}`, recoverable via recycle bin) before `purge` (physical, irreversible, gated by permission checks).
4. See [docs/ACCESS_MAP.md](ACCESS_MAP.md) for the full access map.

---

## 7. Reference Docs

- [docs/ACCESS_MAP.md](ACCESS_MAP.md) — Full access map of running services (URLs / credentials / API docs / endpoint lists)
- [docs/ENVIRONMENT.md](ENVIRONMENT.md) — Complete environment variable & feature-flag reference
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — Architecture overview
- [docs/java-backend.md](java-backend.md) — Java backend dev guide
- [docs/python-ai.md](python-ai.md) — Python AI dev guide
- [docs/PRODUCTION_OPS.md](PRODUCTION_OPS.md) — Production operations guide
