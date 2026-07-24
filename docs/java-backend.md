# Java 后端开发指南

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
├── controller/      # REST controllers
├── dto/             # Data transfer objects
├── entity/          # MyBatis Plus entities
├── enums/           # Domain enums
├── handler/         # Type handlers
├── mapper/          # MyBatis Plus mappers
├── scheduler/       # Scheduled recovery/cleanup tasks
└── service/         # Service interfaces + implementations
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
| `SPRING_DATASOURCE_URL` | Required in containers; overrides local `localhost` MySQL URL |
| `SPRING_DATA_REDIS_HOST` | Required in containers; overrides local Redis host |
| `SPRING_DATA_REDIS_PORT` | Redis port (default: `6379`) |
| `PYTHON_AI_INTERNAL_TOKEN` | Shared secret for Java ↔ Python communication |
| `CALLBACK_SECRET` | HMAC secret for Python → Java callbacks |
| `ADMIN_PASSWORD` | Bootstrap admin account password |
| `AI_SERVICE_URL` | Python AI service URL used by `AiClient` |
| `PYTHON_AI_CALLBACK_BASE_URL` | Java callback base URL reachable from Python |

## Flyway Migrations

Current migrations: **V1–V83**

Rules:
- **Historical migrations (V1–V83) must NOT be modified** — any schema changes go into new `V84+` scripts.
- In production, **never** manually edit `flyway_schema_history`.
- For local dev reset: `docker compose down -v && docker compose up -d` (see [startup-guide.md](startup-guide.md#4-本地重置数据库)).

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
