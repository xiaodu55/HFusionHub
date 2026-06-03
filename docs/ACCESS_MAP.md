# HFusionHub 访问地图 / Access Map

> 本文档是**已启动服务的完整访问清单**：浏览器网址、登录凭据、API 文档、全部接口/路由/页面路径。
> 由 2026-08-21 全栈启动验收时实测生成（`java-live.log` / `docker ps` / `/api/v3/api-docs` / `/openapi.json` / 前端 router 交叉核对）；2026-08-28 增补第十四轮 P2 商业化（套餐/模板/开放 API）。
>
> ⚠️ 本文档**不保存任何明文凭据**：所有密码/令牌请到 `docker/.env`（已 gitignore）查看。生产部署必须全部换新。

---

## 1. 本次启动方式（重要）

- **基础设施**：Dev Docker Compose（`docker/docker-compose.yml`）—— 7 个容器，均为 `docker ps` 中可直接看到的名称。
- **应用层**：Java / Python / 前端是**本地进程**（`scripts/restart-modules.ps1` 启动），**不是容器**。
- **无网关**：本次没有 nginx / caddy / traefik（生产 compose `deploy/docker-compose.prod.yml` 才有 `caddy`）。所有服务直接暴露在 localhost 端口。

## 2. 浏览器可访问的全部网址

| 服务 | 地址 | 说明 |
| :--- | :--- | :--- |
| 前端主界面 | http://localhost:3000 | 登录后使用全部功能 |
| Java API 文档（Knife4j） | http://localhost:8080/api/doc.html | ⭐ 267 个接口可视化/调试 |
| Java Swagger UI 备用 | http://localhost:8080/api/swagger-ui/index.html | 同上（Knife4j 底层） |
| Java OpenAPI JSON | http://localhost:8080/api/v3/api-docs | 机器可读（接口清单数据源） |
| Python API 文档（FastAPI Swagger） | http://localhost:9000/docs | ⭐ 70 个路由交互式调试 |
| Python Redoc | http://localhost:9000/redoc | 只读文档 |
| Python OpenAPI JSON | http://localhost:9000/openapi.json | 机器可读 |
| MinIO 控制台 | http://localhost:9001 | 对象存储管理（API 端口 :9002） |
| Attu（Milvus 管理台） | http://localhost:8000 | 向量库可视化，连接 `127.0.0.1:19530` |

### 纯 API（无界面，供脚本/健康检查）

| 端点 | 说明 |
| :--- | :--- |
| http://localhost:8080/api/actuator/health | Java 健康检查（200 = UP） |
| http://localhost:8080/api/actuator/metrics | Java 指标（Micrometer） |
| http://localhost:8080/api/actuator/prometheus | Java Prometheus 指标 |
| http://localhost:9000/health | Python 健康检查（200 = healthy） |
| http://localhost:9000/ready | Python 就绪检查 |
| http://localhost:9000/metrics | Python 指标 |
| http://localhost:9091/healthz | Milvus HTTP 健康检查 |
| http://localhost:9100/health | Plugin Runner（dev 下 503 = 设计行为，见 reason 字段） |

## 3. 登录凭据

> **密码一律在 `docker/.env` 查看，本文档不保留明文**（避免真实凭据进入 Git 历史）。以下是账号与来源变量的对应关系。

| 系统 | 账号 | 密码来源 | 对应 `docker/.env` 变量 |
| :--- | :--- | :--- | :--- |
| 前端主系统 :3000 | `admin` | `docker/.env` | `ADMIN_PASSWORD` |
| MinIO :9001 | `minioadmin`（或自定义） | `docker/.env` | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |
| Attu :8000 | 无登录 | 连接 `localhost:19530`，db `default` | — |
| MySQL :3306 | root | `docker/.env` | `MYSQL_ROOT_PASSWORD` |
| MySQL 应用库 `hfusionhub` | hfusionhub | `docker/.env` | `MYSQL_PASSWORD` |
| Redis :6379 | — | `docker/.env` | `REDIS_PASSWORD` |

**内部互信令牌**（Java ↔ Python 调用，不用于登录；值在 `docker/.env`）：`PYTHON_AI_INTERNAL_TOKEN`、`CALLBACK_SECRET`、`PLUGIN_RUNNER_TOKEN`

## 4. Java 后端接口（267 个）

- **完整接口列表与请求/响应结构**：浏览器打开 http://localhost:8080/api/doc.html（Knife4j，含 Try it out）。
- **分组概览**（均以 `/api` 为前缀）：

| 模块 | Controller | 接口数 | 前缀 |
| :--- | :--- | :--- | :--- |
| 用户/认证 | UserController | 11 | `/user/*` |
| 知识库 | KnowledgeBaseController + KbShareController | 12 | `/knowledge-base/*` |
| 文档 | DocumentController | 14 | `/document/*` |
| 向量化 | VectorizationController | 9 | `/vectorize/*` |
| 会话/聊天 | ConversationController | 13 | `/conversation/*` |
| Agent 任务 | AgentTaskController | 17 | `/agent-task/*` |
| Agent 可观测性 | AgentObservabilityController | 25 | `/agent-observability/*` |
| RAG 可观测性 | RagObservabilityController | 8 | `/rag/*` |
| RAG 意图树 | RagIntentTreeController | 6 | `/rag/intent-tree/*` |
| RAG 反馈 | RagAnswerFeedbackController | 2 | `/rag/feedback` |
| 应用/发布 | AppController | 10 | `/app/*` |
| 对外 API | OpenApiController | 2 | `/openapi/chat` `/openapi/bid/check` |
| 套餐目录 | BidPlanController | 8 | `/bid/plan/catalog` `/bid/plan/current` `/bid/plan/bind` `/bid/plan/unbind` `/bid/plan/admin*` |
| 标书模板 | BidTemplateController | 5 | `/bid/template/list` `/bid/template/*` |
| 插件 | PluginController | 15 | `/plugin/*` |
| Prompt 模板 | PromptTemplateController | 14 | `/prompt-templates/*` |
| Prompt 测试集 | PromptTestSetController | 16 | `/prompt-test-sets/*` |
| 租户/配额 | TenantController + TenantMemberController + QuotaController | 11 | `/tenant/*` `/quota/*` |
| 工具/MCP | ToolController | 6 | `/tools/*` |
| Feature Flag | FeatureFlagController | 11 | `/feature-flag/*` |
| 记忆/笔记 | MemoryController + NoteController | 9 | `/memory/*` `/note/*` |
| 通知/Webhook | NotificationController + WebhookController | 14 | `/notifications/*` `/webhook/*` |
| 模型配置/成本/系统 | UserModelConfigController + CostController + SystemController | 10 | `/model-config` `/cost/*` `/system/*` |
| 管理/其他 | AuditController + VectorReconciliationController + EvaluationGateController + DemoController + HealthController | 12 | `/admin/*` `/evaluation/*` `/demo/*` `/health` |
| 投标项目 | BidProjectController + BidWriteController + BidCheckController | 14 | `/bid/project/*` `/bid/write*` `/bid/check*` |

- **内部接口**（Java→Java 或内网，不对浏览器开放）：`AgentApprovalInternalController`、`AgentTaskEventController`、`FeatureFlagInternalController`、`InternalNoteController`、`InternalPluginController`、`InternalPluginQuotaController`。
- 认证：登录 `POST /api/user/login` 拿 `data`（Sa-Token），后续请求带 header `satoken: <token>`。无 token 访问受保护接口返回 401。

## 5. Python AI 路由（70 个）

- **完整交互式文档**：http://localhost:9000/docs（或 /redoc）。
- 核心入口：
  - 聊天：`POST /api/chat` / `POST /api/chat/stream`（SSE）/ `POST /api/chat/cancel`
  - Agent：`POST /api/agent/v1/chat` / `.../stream` / `.../decide`
  - 解析：`POST /api/parse`；检索：`POST /api/search`；调试检索：`POST /api/rag/debug/search`
- 全部路由经 Java 代理访问（Java 带 `X-Internal-Token`）；直连需带 `X-Internal-Token: <PYTHON_AI_INTERNAL_TOKEN>` 头，否则 401/403。

## 6. 前端页面（42 个路由）

| 分组 | 路径 |
| :--- | :--- |
| 认证 | `/login` `/register` `/pending-approval` |
| 首页 | `/` |
| 知识库 | `/knowledge-base` `/knowledge-base/recycle-bin` `/knowledge-base/:id` `/knowledge-base/:id/chunks/:docId` |
| 文档 | `/document` `/document/recycle-bin` |
| 聊天 | `/chat` `/chat/:id` |
| Agent | `/agent` `/approvals` |
| 构建器 | `/builder/prompts` `/builder/prompts/recycle-bin` `/builder/models` `/builder/tools` `/builder/plugins` `/builder/test-bench` `/builder/test-sets` `/builder/apps` `/builder/mcp` |
| 成本/记忆/笔记/RAG | `/cost` `/memory` `/notes` `/rag` |
| 投标项目 | `/bid/projects` `/bid/projects/:id/interpret` `/bid/projects/:id/requirements` `/bid/projects/:id/draft` |
| 套餐中心 | `/bid/billing` |
| 个人/设置 | `/profile` `/settings` |
| 管理 | `/admin/flags` `/admin/intent-tree` `/admin/users` `/admin/notices` `/admin/audit-logs` `/admin/plans` |

## 7. 容器端口速查

| 容器 | 端口 | 状态 |
| :--- | :--- | :--- |
| mysql8 | 3306 | healthy |
| redis7 | 6379 | healthy |
| minio | 9001（Console）/ 9002（API） | healthy |
| etcd | 2379 | healthy |
| milvus | 19530（gRPC）/ 9091（HTTP） | healthy |
| attu | 8000 | healthy |
| plugin-runner | 9100 | dev 下 unhealthy（503，设计行为） |

## 8. 相关文档

- [startup-guide.md](startup-guide.md) — 启动/重启/排障
- [SWAGGER_UI.md](SWAGGER_UI.md) — Knife4j/Swagger 配置与生产关闭策略
- [ENVIRONMENT.md](ENVIRONMENT.md) — 环境变量唯一权威
- [api.md](api.md) — API 接口参考

---

**最后更新**：2026-08-28（增补 P2 商业化：套餐目录/模板商城/开放 API 结算）
