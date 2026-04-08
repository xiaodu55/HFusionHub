# HFusionHub First-Time Setup & Startup Guide

> Covers **first-time setup after a fresh clone** as well as daily startup, restart, and troubleshooting. For production deployment see `deploy/docker-compose.prod.yml` and `docs/ENVIRONMENT.md`.

---

## 0. Prerequisites

| Dependency | Version | Notes |
| :--- | :--- | :--- |
| Java | 17+ | Spring Boot 3.2 runtime |
| Python | 3.11+ | AI service runtime |
| Node.js | 20.19+ or 22.12+ | Vite 8 dev server |
| Docker | Desktop / Engine | MySQL, Redis, MinIO, Plugin Runner |
| Maven | 3.8+ (or use `mvnw`) | Java backend build |

---

## 1. First-Time Setup (Fresh Clone)

### 1.1 Clone the Repository

```bash
git clone https://github.com/xiaodu55/HFusionHub.git
cd HFusionHub
```

### 1.2 Create Environment Files

The project uses `.env` files for secrets — these are **not committed to Git**. Copy from the example templates:

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
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:8b-fp16
# Note: the variable is OLLAMA_EMBEDDING_MODEL, not the deprecated OLLAMA_MODEL

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

### 1.5 Start Docker Infrastructure

```powershell
cd docker
docker compose up -d
```

Wait for all containers to be healthy:

```powershell
docker compose ps
# All four containers (mysql8, redis7, minio, plugin-runner) should show healthy/running
```

**Docker services**:

| Service | Port | Purpose |
| :--- | :--- | :--- |
| MySQL 8.0 | `127.0.0.1:3306` | Business database |
| Redis 7 | `127.0.0.1:6379` | Cache & sessions |
| MinIO | `127.0.0.1:9002` (API), `9001` (Console) | Object storage |
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

On first launch, Flyway automatically runs `V1`–`V35+` migration scripts to create all tables.

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
| MySQL | `localhost:3306` | `docker compose ps` (in `docker/` directory), status healthy |
| Redis | `localhost:6379` | `docker compose ps`, status healthy |
| MinIO Console | http://localhost:9001 | Open in browser, log in with credentials from `docker/.env` |
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
| 2 | Java backend | `cd java-backend && mvn spring-boot:run` |
| 3 | Python AI | `cd python-ai && .\.venv\Scripts\Activate.ps1 && python -m app.main` |
| 4 | Frontend | `cd hfusionhub-frontend && npm run dev` |

### 2.2 Java Backend (Quick Start)

```powershell
cd java-backend
$env:DB_USERNAME="hfusionhub"
$env:DB_PASSWORD="<same as MYSQL_PASSWORD>"
$env:CALLBACK_SECRET="<same secret used by Python>"
$env:PYTHON_AI_INTERNAL_TOKEN="<same token used by Python>"
$env:ADMIN_PASSWORD="<admin bootstrap password>"
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
| MySQL / Redis config only | Docker infrastructure |

---

## 4. Local Database Reset

This **deletes** local MySQL data — all data will be lost:

```powershell
cd docker
docker compose down -v
docker compose up -d
```

After reset, restart Java so Flyway can recreate the schema (`V1`–`V35+`).

> ⚠️ For future schema changes, create new `V36+` migration files. **Do not modify existing migrations**, or Flyway will report a checksum mismatch.

---

## 5. Production Notes

`deploy/docker-compose.prod.yml` already sets container service URLs:

- `SPRING_DATASOURCE_URL=jdbc:mysql://mysql8:3306/hfusionhub?...`
- `SPRING_DATA_REDIS_HOST=redis7`
- `AI_SERVICE_URL=http://python-ai:9000`
- `PYTHON_AI_CALLBACK_BASE_URL=http://java-backend:8080/api`
- `LLM_ALLOW_MOCK=false`
- `EMBEDDING_ALLOW_FALLBACK=false`

The Helm template already includes equivalent Java environment overrides and is production-ready.

---

## 6. Common Issues

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| Java → Python returns 401/403 | `PYTHON_AI_INTERNAL_TOKEN` mismatch | Verify the token is identical in both terminals |
| Python → Java callback fails | `CALLBACK_SECRET` mismatch or network issue | Verify `CALLBACK_SECRET` matches and Python can reach Java |
| Document indexing fails | No embedding service available | Configure Ollama (`OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL`); or temporarily set `EMBEDDING_ALLOW_FALLBACK=true` |
| Flyway checksum mismatch | Existing migration files were modified | For local dev, use §4 to reset DB; in production, create a new migration script |
| Database connection failed | `DB_PASSWORD` doesn't match `MYSQL_PASSWORD` | Ensure Java's `DB_PASSWORD` matches `docker/.env`'s `MYSQL_PASSWORD` |
| `npm ci` fails | Node.js version too old/new | Use `nvm` to switch to Node.js 20.19+ or 22.12+ |
| Docker containers not all healthy | Startup order or resource contention | Wait 30s and `docker compose ps`; `docker compose restart` if needed |
| `.env` file not found | Not created after fresh clone | Run `copy docker\.env.example docker\.env` and `copy python-ai\.env.example python-ai\.env` |

---

## 7. Reference Docs

- [docs/ENVIRONMENT.md](ENVIRONMENT.md) — Complete environment variable reference
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — Architecture overview
- [docs/启动重启1.md](启动重启1.md) — Chinese startup guide
- [docs/java-backend.md](java-backend.md) — Java backend dev guide
- [docs/python-ai.md](python-ai.md) — Python AI dev guide
- [docs/PRODUCTION_OPS.md](PRODUCTION_OPS.md) — Production operations guide
