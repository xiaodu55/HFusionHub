# Contributing to HFusionHub

Thank you for your interest in contributing! This document outlines the development workflow.

## Getting Started

See [docs/startup-guide.md](docs/startup-guide.md) for the complete bilingual startup guide (中文 + English).

### Quick Start

```bash
# 1. Infrastructure
cd docker
docker compose up -d

# 2. Python AI (terminal 1)
cd python-ai
python -m venv .venv && source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
python -m app.main

# 3. Java Backend (terminal 2)
cd java-backend
mvn spring-boot:run

# 4. Frontend (terminal 3)
cd hfusionhub-frontend
npm ci && npm run dev
```

## Development Workflow

1. **Fork** the repository
2. **Create a branch**: `feature/your-feature` or `fix/your-fix`
3. **Make changes** following the existing code style
4. **Run tests** to verify nothing is broken
5. **Commit** with a descriptive message
6. **Push** and create a Pull Request

## Code Style

### Java
- Follow standard Java conventions
- Use Lombok where appropriate (`@Slf4j`, `@Data`, etc.)
- Service layer: interface + implementation pattern
- Controllers return `Result<T>` wrapper

### Python
- Follow PEP 8
- Use type hints
- Strategy pattern for swappable implementations
- Pydantic models for request/response validation

### Frontend
- Vue 3 Composition API with `<script setup lang="ts">`
- Tailwind CSS for styling, Radix Vue for accessible primitives
- Pinia for state management
- Axios with sa-token header injection

## Running Tests

```bash
# Java
cd java-backend && mvn test

# Python (1220+ tests)
cd python-ai && pytest -q tests

# Frontend (unit tests + type check + build)
cd hfusionhub-frontend && npm run test && npm run build
```

## Flyway Migrations

- **Never modify** existing migration files (V1–V57)
- Create new `V58+` scripts for schema changes
- See [docs/database.md](docs/database.md) for migration rules

## Documentation

- Chinese docs: `docs/` directory (README-style guides)
- English docs: `docs/` directory (architecture, API reference)
- Inline code comments: prefer Chinese for domain logic, English for API/interface docs

## Questions?

- Check existing [docs/](docs/) first
- Search closed issues before opening a new one
- For AI/agent behavior questions, check the [RAG engine docs](docs/python-ai.md#rag-pipeline-in-order)
