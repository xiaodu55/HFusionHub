# Java Backend Development Guide

> Spring Boot 3.2.5 + MyBatis Plus + MySQL + Redis + Sa-Token

## Architecture

The Java backend owns the **write path** — user authentication, CRUD operations, file uploads, conversation persistence, and task scheduling. It proxies AI requests to the Python AI service.

```
Controller → Service → Mapper (MyBatis Plus) → MySQL
                ↕
           AiClient (HTTP) → Python AI (:9000)
```

## Project Structure

```
java-backend/src/main/java/com/hfusionhub/
├── client/          # AiClient — HTTP calls to Python AI service
├── common/          # Constants, exceptions, utils, DTOs
├── config/          # Spring config (Sa-Token, Admin init, etc.)
├── controller/      # REST controllers (7 controllers)
├── dto/             # Data transfer objects (17 classes)
├── entity/          # JPA entities (8 classes)
├── enums/           # DocumentStatus enum
├── handler/         # JsonTypeHandler
├── mapper/          # MyBatis Plus mappers (8 mappers)
├── scheduler/       # Scheduled tasks (4 schedulers)
└── service/         # Service interfaces + implementations (6 pairs)
```

## Key Design Patterns

| Pattern | Where | Purpose |
|---------|-------|---------|
| CQRS-like | Java ↔ Python boundary | Java owns writes (ACID), Python owns reads/retrieval |
| HMAC-signed callbacks | `VectorizationController` | Python → Java document processing results |
| Durable outbox | `deletion_task` table | Async cleanup with retry |
| Idempotent indexing | `document_index_job.index_version` | Prevents duplicate vectorization |

## Configuration

- **Database**: `application.yml` — `spring.datasource` (MySQL 8.0)
- **Flyway**: `spring.flyway` — migrations in `db/migration/V*.sql`
- **Auth**: `sa-token` — JWT-based, 86400s timeout, 1800s active timeout
- **Python AI**: `python-ai.*` — base URL, callback secret, internal token

## Required Environment Variables

| Variable | Description |
|----------|-------------|
| `DB_USERNAME` | MySQL username (default: `hfusionhub`) |
| `DB_PASSWORD` | MySQL password (must match `MYSQL_PASSWORD`) |
| `PYTHON_AI_INTERNAL_TOKEN` | Shared secret for Java ↔ Python communication |
| `CALLBACK_SECRET` | HMAC secret for Python → Java callbacks |
| `ADMIN_PASSWORD` | Bootstrap admin account password |

## Flyway Migrations

Current migrations: **V1–V7**

Rules:
- **Historical migrations (V1–V7) must NOT be modified** — any schema changes go into new `V8+` scripts.
- In production, **never** manually edit `flyway_schema_history`.
- For local dev reset: `docker compose down -v && docker compose up -d` (see `启动重启1.md` §9).

## Running Tests

```bash
cd java-backend
mvn test                          # Run all tests
mvn test -Dtest=ClassName         # Run specific test class
```

Tests use H2 in-memory database (MySQL compatibility mode) by default.

## Building

```bash
# First time (download dependencies + package without tests)
mvn -DskipTests package

# Development (run directly)
mvn spring-boot:run

# Run packaged JAR (faster startup)
java -jar target/hfusionhub-backend-1.0.0-SNAPSHOT.jar
```

## API Documentation

Once running, visit: http://localhost:8080/api/doc.html (Knife4j / Swagger UI)
