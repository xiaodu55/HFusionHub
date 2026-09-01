# Java 后端开发指南

> Spring Boot 3.5.16 + MyBatis Plus + MySQL + Redis + Sa-Token

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

## 鉴权体系分工（R17-9）

认证与授权**只有一套**：Sa-Token。`common/utils/JwtUtils.java` 名字带
Jwt 是历史遗留——它**不含任何 JWT 解析**，实为 Sa-Token 的静态薄包装 +
`StpInterface` 权限数据源。职责边界：

| 关注点 | 归属 | 说明 |
|---|---|---|
| 登录态认证 | `SaTokenConfig` 拦截器 | checkLogin + 未分配角色审批门 |
| 粗粒度角色门 | 拦截器 | 未分配角色只读 |
| 细粒度授权 | `@SaCheckPermission/@SaCheckRole` 注解（约 14 个 controller） | 权限数据源 = JwtUtils（StpInterface 回调） |
| 读当前用户 ID | `JwtUtils.getCurrentUserId()`（~158 处） | 事实上的标准读法，勿直接用 StpUtil |
| 服务层角色判断 | `JwtUtils.hasRole()` | 少量 service 场景 |

新代码规则：**认证/授权一律走 Sa-Token 注解与拦截器；读用户 ID 一律
`JwtUtils.getCurrentUserId()`；不要再新增 StpUtil 直接调用**（现存仅
SaTokenConfig/JwtUtils/OidcService/FeatureFlagServiceImpl 四处）。

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

Current migrations: **V1–V85**

Rules:
- **Historical migrations (V1–V85) must NOT be modified** — any schema changes go into new `V86+` scripts.
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
