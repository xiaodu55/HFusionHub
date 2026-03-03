# API Documentation

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

## Python AI Public Endpoints

### MCP (`/mcp`) — No internal token required for discovery
- `POST /` — JSON-RPC 2.0 endpoint (initialize, tools/list, tools/call)
- `GET /health` — MCP server health and tool count
- `GET /tools` — List available tool schemas

> `tools/call` requires `X-Internal-Token` header. `search_knowledge_base` additionally requires `X-HFusionHub-KB-ID`.

### Metrics (`/metrics`)
- `GET /` — Prometheus text format metrics (requests, latency, errors)
- `GET /json` — Human-readable JSON snapshot

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
