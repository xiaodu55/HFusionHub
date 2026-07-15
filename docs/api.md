# API 文档

> REST API + SSE streaming + Knife4j (Swagger UI)

## Interactive API Docs

Once the Java backend is running, visit:

🔗 **http://localhost:8080/api/doc.html** (Knife4j / Swagger UI)

This provides interactive documentation for all REST endpoints with request/response examples.

## Authentication

HFusionHub uses **Sa-Token** (JWT-based) for authentication.

### Login

```bash
curl -s -X POST http://localhost:8080/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}'
```

Response:
```json
{
  "code": 200,
  "data": {
    "tokenName": "satoken",
    "tokenValue": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "userId": 1,
    "username": "admin"
  }
}
```

### Authenticated Requests

Include the token in all subsequent requests:
```
satoken: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### Public Endpoints (no auth required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/user/login` | User login |
| POST | `/api/user/register` | User registration |
| GET | `/api/health` | Health check |
| POST | `/api/vectorize/*/callback` | Python AI callback (HMAC-signed) |

## API Modules

### User (`/api/user`)
- `POST /login` — Login
- `POST /register` — Register
- `POST /logout` — Logout
- `GET /info` — Get current user profile
- `PUT /info` — Update profile (nickname/email/phone)
- `POST /password` — Change own password (old password required)
- `POST /avatar` — Upload avatar (multipart, jpg/png/webp/gif ≤2MB; magic bytes validated)
- `GET /avatar/{userId}` — Fetch avatar image (auth required; frontend loads via fetch+blob)

### Knowledge Base (`/api/knowledge-base`)
- `POST /` — Create knowledge base
- `GET /` — List knowledge bases
- `GET /{id}` — Get knowledge base detail
- `PUT /{id}` — Update knowledge base
- `DELETE /{id}` — Delete knowledge base

### Document (`/api/document`)
- `POST /upload` — Upload document (multipart/form-data)
- `GET /` — List documents
- `GET /{id}` — Get document detail
- `DELETE /{id}` — Soft-delete to recycle bin
- `POST /{id}/restore` — Restore from recycle bin

### Conversation (`/api/conversation`)
- `POST /` — Create conversation
- `GET /` — List conversations
- `GET /{id}` — Get conversation with messages
- `POST /message` — Send message (non-streaming)
- `POST /message/stream` — Send message (SSE streaming)
- `POST /message/stream/cancel` — Cancel streaming response

### RAG Observability (`/api/rag`)
- `GET /traces` — List retrieval traces (with pagination and filters)
- `GET /traces/stats` — Trace statistics
- `GET /traces/export` — Export traces as CSV
- `GET /traces/{traceId}` — Get single trace detail
- `POST /evaluate` — Run retrieval evaluation
- `GET /evaluation-runs` — List evaluation run history

### Memory (`/api/memory`)
- `GET /` — List memories (filter by type, conversationId)
- `POST /` — Save a memory entry
- `DELETE /{id}` — Delete a memory entry

### System Diagnostics (`/api/system`)
- `GET /ai-health` — Preflight check: Python AI reachability, token config, upload directory, embedding status

### Notifications (`/api/notifications`)
- `GET /` — List active notices for current user
- `GET /unread-count` — Get unread notification count
- `POST /{id}/read` — Mark a notice as read

### Health
- `GET /api/health` — Service health check

## Open API（应用发布 · 外部系统对接）

通过「应用发布」创建应用并生成 API Key（`hf_` 前缀，在 `builder/apps` 页面管理）后，外部系统无需登录即可调用。鉴权支持两种头（二选一）：

- `Authorization: Bearer hf_xxx`
- `X-API-Key: hf_xxx`

计量计费（token 用量计入租户 usage ledger）与限流对开放 API 同样生效。

### 应用对话 (`POST /api/openapi/chat`)

```bash
curl -X POST http://localhost:8080/api/openapi/chat \
  -H "Authorization: Bearer ***REMOVED-BY-REWRITE***" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "介绍一下产品的主要特点",
    "history": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好，有什么可以帮你？"}]
  }'
```

响应：

```json
{
  "content": "根据知识库内容，产品的主要特点包括……",
  "sources": [{"document_name": "产品手册.pdf", "score": 0.87}],
  "model": "deepseek-v4-flash",
  "status": "success",
  "tokenUsage": {"inputTokens": 120, "outputTokens": 356}
}
```

### 投标废标自检 (`POST /api/openapi/bid/check`)

```bash
curl -X POST http://localhost:8080/api/openapi/bid/check \
  -H "X-API-Key: ***REMOVED-BY-REWRITE***" \
  -H "Content-Type: application/json" \
  -d '{"projectId": 42}'
```

需应用所在租户开通 openapi 模块；响应为废标自检报告（severity/status/issues 列表等）。

### 管理接口补充（会话鉴权，非开放 API）

- `PUT /api/user/{userId}/password` — 管理员重置用户密码（仅 admin；不可用于自己；body: `{"newPassword": "6-64位临时密码"}`）

## Python AI Public Endpoints

### MCP (`/mcp`) — No internal token required for discovery
- `POST /` — JSON-RPC 2.0 endpoint (initialize, tools/list, tools/call)
- `GET /health` — MCP server health and tool count
- `GET /tools` — List available tool schemas

> `tools/call` requires `X-Internal-Token` header. `search_knowledge_base` additionally requires `X-HFusionHub-KB-ID`.

### Metrics (`/metrics`)
- `GET /` — Prometheus text format metrics (requests, latency, errors)
- `GET /json` — Human-readable JSON snapshot

### Analytics (`/api/analytics`) — 分析扩展包（HFusionData Analytics）

- `GET /overview?days=7` — 概览：近 N 天累计调用/Token/成本 + 近 5 分钟实时速率
- `GET /cost-daily?days=7&tenantId=` — 每日成本趋势（Spark ADS 镜像）
- `GET /model-share?date=&tenantId=` — 模型成本占比（默认 T-1）
- `GET /tool-success?days=7&tenantId=` — Agent 步骤成功率
- `GET /eval-quality?days=30&tenantId=` — 检索/评测质量趋势
- `GET /realtime?minutes=60&tenantId=` — 实时指标（1 分钟窗口，Flink 聚合）

租户隔离在服务端强制：普通用户仅本租户数据；平台管理员（crossTenant 会话）
可传 `tenantId` 查指定租户或 `-1` 平台全局。扩展包未部署时返回空集而非报错。
内部回补端点：`POST /api/internal/analytics/batch/run`（X-Internal-Token 保护，
body `{"date":"YYYY-MM-DD"}`，触发 Sqoop→Spark→质量门禁→ADS 管线）。

## Internal API (Python AI ↔ Java)

Communication between Java and Python uses:
- **Header**: `X-Internal-Token: <PYTHON_AI_INTERNAL_TOKEN>`
- **Callback HMAC**: Python signs callbacks with `CALLBACK_SECRET`

These endpoints are not exposed publicly and require the internal token.

## Context Path

All API paths are prefixed with `/api` (configured via `server.servlet.context-path=/api`).

- Browser request: `http://localhost:8080/api/health`
- Spring interceptor matches: `/health` (context-path stripped)

## Frontend Proxy

The Vite dev server proxies `/api` requests to `localhost:8080` (configured in `vite.config.ts`).
