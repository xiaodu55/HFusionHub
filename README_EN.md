# HFusionHub

> An enterprise-grade AI Agent platform with a hybrid Java + Python architecture.

[简体中文](./README.md) | English

![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)
![Java](https://img.shields.io/badge/Java-17%2B-orange)
![Python](https://img.shields.io/badge/Python-3.11%2B-green)
![Vue](https://img.shields.io/badge/Vue-3-42b883)

## Overview

HFusionHub pairs the reliability of a Java backend (ACID writes, tenancy, billing) with the flexibility of the Python AI ecosystem (RAG, agents, streaming intelligence). It ships a complete RAG + Agent solution with a modern web console.

## Architecture

Three-tier hybrid:

- **Java backend** (`java-backend/`) — owns all writes: Spring Boot 3.x, MyBatis Plus, MySQL, Redis, Flyway migrations, multi-tenancy, usage ledger and quota enforcement.
- **Python AI layer** (`python-ai/`) — owns reads and intelligence: FastAPI, Milvus (standalone via Docker), ReAct agent loop, retrieval pipelines, embedding and model gateways.
- **Web console** (`hfusionhub-frontend/`) — Vue 3 + Vite + TypeScript + Tailwind CSS.

Java ↔ Python internal endpoints are protected by `X-Internal-Token` / HMAC-signed callbacks.

## Highlights

- **Agent core**: ReAct loop, multi-agent collaboration, human-in-the-loop tool approvals with durable one-time execution tokens, checkpoints, SSE streaming with structured events.
- **RAG engine**: hybrid retrieval (vector + BM25), parent-child chunking, semantic chunking (experimental), query decomposition, context compression, self-reflection, groundedness and citation integrity checks.
- **Model gateway**: DeepSeek / Ollama / OpenAI-compatible providers with automatic failover, circuit breaking, rate limiting and token billing.
- **Build center**: prompt workbench with version history, model hub, tool hub, plugin sandbox.
- **Ops center**: cost dashboards, tool approvals, RAG observability, long-term memory.
- **Safety guardrails**: prompt-injection detection, content moderation, PII masking (demo mode).
- **Voice (experimental)**: STT/TTS wired end-to-end behind `VOICE_ENABLED`.

## Quick start

```bash
# 1. Configure and start the infrastructure stack (MySQL, Redis, Milvus, observability)
cp docker/.env.example docker/.env   # fill in model provider keys
docker compose up -d                 # from the docker/ directory

# 2. Java backend (port 8080)
cd java-backend && mvn spring-boot:run

# 3. Python AI service (port 9000) + arq worker for async document parsing
cd python-ai
.venv/Scripts/python.exe -m app.main            # Linux/macOS: .venv/bin/python -m app.main
.venv/Scripts/python.exe -m arq app.core.tasks.arq_tasks.WorkerSettings

# 4. Web console (port 3000, dev proxy → 8080)
cd hfusionhub-frontend && npm install && npm run dev
```

Environment variables are documented in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

## Verification

```bash
cd java-backend && mvn test                      # 702 tests (H2 in-memory, Flyway-checked)
cd python-ai && .venv/Scripts/activate && pytest -q tests
cd hfusionhub-frontend && npm run build && npx vitest run
python scripts/static-checks.py                  # cross-repo consistency gates
```

## Documentation

The full documentation index lives in the [Chinese README](./README.md#文档索引-documentation-index) — architecture, database, environment, CI gates, demo script and more.

## License

Apache-2.0
