# Database Design

> MySQL 8.0 + Flyway migrations + MyBatis Plus ORM

## Overview

The database `hfusionhub` is managed via Flyway migrations in `java-backend/src/main/resources/db/migration/`.

## Migration History

| Version | File | Description |
|---------|------|-------------|
| V1 | `V1__initial_schema.sql` | Core tables (user, knowledge_base, document, conversation, message, document_index_job) |
| V2 | `V2__document_index_persistence.sql` | Document index job enhancements |
| V3 | `V3__deletion_task_outbox.sql` | Durable deletion outbox pattern |
| V4 | `V4__message_request_id.sql` | Idempotency via request_id on messages |
| V5 | `V5__remove_default_admin.sql` | Remove hardcoded default admin |
| V6 | `V6__add_document_processed_at.sql` | Document processing timestamps |
| V7 | `V7__document_recycle_bin.sql` | Soft-delete recycle bin for documents |
| V8 | `V8__persistent_memory.sql` | Persistent AI memory entries |

## Migration Rules

1. **Historical migrations (V1–V8) are immutable.** Never modify them.
2. **All future schema changes must use new V9+ scripts.**
3. **Production**: Never manually edit `flyway_schema_history`. Create new migration scripts.
4. **Local dev reset**: `docker compose down -v && docker compose up -d` clears the database.

### Checksum Mismatch Fix (Local Dev Only)

If you encounter `Migration checksum mismatch` during local development:

```powershell
# Reset database (loses all data)
cd docker
docker compose down -v
docker compose up -d

# OR: fix checksums (keep data)
# See docs/启动重启1.md, section 9, for exact reset commands
```

## Core Tables

| Table | Purpose |
|-------|---------|
| `sys_user` | User accounts and auth |
| `knowledge_base` | Knowledge base metadata and ownership |
| `document` | Uploaded documents with status tracking |
| `document_chunk` | Parsed and vectorized text chunks |
| `document_index_job` | Async indexing job tracking |
| `conversation` | Chat conversations |
| `message` | Individual messages with source citations |
| `deletion_task` | Durable deletion outbox for async cleanup |
| `memory_entry` | Persistent conversation summaries, entity facts, and user preferences |

## Entity Relationships

```
sys_user (1) ──→ (N) knowledge_base
knowledge_base (1) ──→ (N) document
document (1) ──→ (N) document_chunk
document (1) ──→ (N) document_index_job
sys_user (1) ──→ (N) conversation
conversation (1) ──→ (N) message
```

## Connection Config

See `java-backend/src/main/resources/application.yml`:
```yaml
spring:
  datasource:
    driver-class-name: com.mysql.cj.jdbc.Driver
    url: jdbc:mysql://localhost:3306/hfusionhub?useUnicode=true&characterEncoding=utf-8&useSSL=false&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true
    username: ${DB_USERNAME:hfusionhub}
    password: ${DB_PASSWORD:}
```

For containerized deployments, override the local default URL with `SPRING_DATASOURCE_URL`, for example `jdbc:mysql://mysql8:3306/hfusionhub?...`. Production Docker Compose already sets this; the Helm template still needs the equivalent override before production use.

## ERD / Visual Schema

For a visual schema reference, connect to the running database with any MySQL client (DBeaver, DataGrip, MySQL Workbench) using:
- Host: `localhost`
- Port: `3306`
- Database: `hfusionhub`
- User: `hfusionhub`
- Password: value of `MYSQL_PASSWORD` from `docker/.env`
