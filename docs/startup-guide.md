# Startup and Restart Guide

> Local development startup, restart, and deployment checks for HFusionHub.

## Prerequisites

- Java 17+
- Python 3.11+
- Node.js 20.19+ or 22.12+
- Docker Desktop / Docker Engine
- MySQL 8.0 and Redis 7 are normally started through `docker/docker-compose.yml`

## 1. Local Infrastructure

Create local secrets. Use your own values and do not commit `.env` files.

```powershell
$env:MYSQL_ROOT_PASSWORD="replace-with-a-strong-root-password"
$env:MYSQL_PASSWORD="replace-with-a-strong-db-password"
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD=$env:MYSQL_PASSWORD
$env:CALLBACK_SECRET="replace-with-a-long-random-callback-secret"
$env:PYTHON_AI_INTERNAL_TOKEN="replace-with-a-long-random-internal-token"
$env:ADMIN_PASSWORD="replace-with-a-strong-admin-password"
```

Start MySQL and Redis:

```powershell
cd docker
docker compose up -d
docker compose ps
```

Local Redis currently runs without password authentication. The `REDIS_PASSWORD` entry in `docker/.env.example` is a placeholder until Redis `requirepass` and Spring `spring.data.redis.password` are wired end to end.

## 2. Java Backend

```powershell
cd ..\java-backend
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD="<same-as-MYSQL_PASSWORD>"
$env:CALLBACK_SECRET="<same-secret-used-by-python>"
$env:PYTHON_AI_INTERNAL_TOKEN="<same-token-used-by-python>"
$env:ADMIN_PASSWORD="<admin-bootstrap-password>"
mvn spring-boot:run
```

Local URL: `http://localhost:8080/api`

Interactive API docs: `http://localhost:8080/api/doc.html`

## 3. Python AI Service

```powershell
cd ..\python-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHON_AI_INTERNAL_TOKEN="<same-token-used-by-java>"
$env:CALLBACK_SECRET="<same-secret-used-by-java>"
$env:DEEPSEEK_API_KEY="<deepseek-api-key>"
$env:JAVA_BACKEND_URL="http://localhost:8080"
python -m app.main
```

Health check: `http://localhost:9000/health`

For document indexing in non-test environments, configure a real embedding provider. The current production path expects Ollama embeddings through `OLLAMA_BASE_URL` and `OLLAMA_EMBEDDING_MODEL`. `DEEPSEEK_API_KEY` is used for chat LLM calls; DeepSeek does not provide the embedding API used by this project. Random-vector embedding fallback is only for development or tests and requires `EMBEDDING_ALLOW_FALLBACK=true`.

## 4. Frontend

```powershell
cd ..\hfusionhub-frontend
npm ci
npm run dev
```

Frontend URL: `http://localhost:3000`

The Vite dev server proxies `/api` to `http://localhost:8080`.

## 5. Restart Order

Use this order after configuration changes:

1. Restart infrastructure only when MySQL/Redis config changed: `cd docker && docker compose restart`
2. Restart Java after changing database, Redis, callback, auth, or AI service environment variables.
3. Restart Python after changing LLM, embedding, RAG, callback, or internal-token environment variables.
4. Restart frontend after changing Vite config or frontend environment.

## 6. Local Reset

This removes local MySQL data:

```powershell
cd docker
docker compose down -v
docker compose up -d
```

After reset, restart Java so Flyway can recreate the schema. Current migrations are `V1` through `V8`; create `V9+` scripts for future schema changes.

## 7. Production Notes

`deploy/docker-compose.prod.yml` already sets container service URLs for MySQL, Redis, Java, and Python:

- `SPRING_DATASOURCE_URL=jdbc:mysql://mysql8:3306/hfusionhub?...`
- `SPRING_DATA_REDIS_HOST=redis7`
- `AI_SERVICE_URL=http://python-ai:9000`
- `PYTHON_AI_CALLBACK_BASE_URL=http://java-backend:8080/api`
- `LLM_ALLOW_MOCK=false`
- `EMBEDDING_ALLOW_FALLBACK=false`

The Helm template still needs equivalent Java environment overrides for database URL, Redis host, and callback base URL before it should be treated as production-ready.

## 8. Common Checks

```powershell
# Docker services
docker ps

# Java health
Invoke-WebRequest http://localhost:8080/api/health

# Python health
Invoke-WebRequest http://localhost:9000/health
```

If Java to Python requests return 401 or 403, verify that `PYTHON_AI_INTERNAL_TOKEN` is identical in both terminals.

If document indexing fails during embedding, verify that Ollama is reachable and has the configured embedding model, or explicitly enable `EMBEDDING_ALLOW_FALLBACK=true` for local testing only.
