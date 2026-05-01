# 容灾手册：向量库迁移

## Overview

HFusionHub uses a dual-store architecture for document chunks:
- **MySQL** (`document_chunk` table): durable citation metadata (chunk_id, document_id, content_excerpt, outline_path, embedding_model/dimension/version)
- **Milvus** (standalone cluster in production): dense vector embeddings for similarity search

The MySQL chunk index is the **source of truth** for document ownership, citation integrity, and reconciliation. Milvus is rebuildable from the original documents; MySQL is not.

---

## Backup Strategy

### MySQL (Primary — daily, automated)
```bash
# Full backup
mysqldump -u root -p --single-transaction --routines --triggers \
  hfusionhub > hfusionhub_mysql_$(date +%Y%m%d_%H%M%S).sql

# Restore
mysql -u root -p hfusionhub < hfusionhub_mysql_YYYYMMDD_HHMMSS.sql
```

### Milvus (Secondary — volume snapshot)

数据卷实际名为 `<project>_milvus-data`（project = compose 文件所在目录名或 `COMPOSE_PROJECT_NAME`）。开发栈为 `docker_milvus-data`，生产栈（`deploy/docker-compose.prod.yml`）为 `deploy_milvus-data`。推荐直接用 `scripts/backup_milvus.sh` / `restore_milvus.sh`：

```bash
# 备份
./scripts/backup_milvus.sh [backup_dir]

# 恢复
./scripts/restore_milvus.sh <backup_file.tar.gz>
```

手动等价命令：

```bash
# Stop Milvus briefly for consistent snapshot
docker compose -f deploy/docker-compose.prod.yml stop milvus

# Snapshot the data volume
docker run --rm -v ${COMPOSE_PROJECT_NAME:-deploy}_milvus-data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/milvus_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Restart Milvus
docker compose -f deploy/docker-compose.prod.yml start milvus
```

### Cluster mode: co-store JSON is not used
Production / staging run in `VECTOR_STORE_MODE=cluster`. BM25 and citations
read their scoped corpus directly from Milvus via `all_chunks()`; there is no
per-pod `chunks_store.json`, so no separate co-store backup is required.

### Lite dev mode (bare-metal only): co-store JSON only
`VECTOR_STORE_MODE=lite` 仅用于本地裸跑（无 Docker）与测试。此时 `python-ai/data/chunks_store.json`
本地 co-store 会被读写，可作为普通文件直接拷贝备份：

```bash
cp python-ai/data/chunks_store.json backups/chunks_store_$(date +%Y%m%d_%H%M%S).json
```

---

## Recovery Procedures

### Scenario 1: Milvus data loss, MySQL intact
1. Milvus volume is corrupt or deleted.
2. MySQL `document_chunk` table has all metadata (embedding_model, embedding_dimension, embedding_version).
3. **Action**: Drop and recreate the Milvus collection. Re-index affected documents from their source files via the Java API.

```bash
# Force collection drop
export MILVUS_ALLOW_COLLECTION_DROP=true
# Trigger re-index for affected documents via the UI or API:
#   POST /api/vectorize/{documentId}/start
```

### Scenario 2: MySQL chunk data loss, Milvus intact
1. `document_chunk` table is empty or corrupt.
2. Milvus has the vectors but no citation metadata.
3. **Action**: Rebuild MySQL from Milvus query results (chunk_id, document_id, knowledge_base_id, content). Content excerpts are in Milvus `content` field. This is a partial recovery — outline_path and metadata may be incomplete.

### Scenario 3: Both stores lost
1. Full rebuild from source documents.
2. Restore MySQL from backup if available, then re-index all documents.

### Scenario 4: Orphan vectors detected (reconciliation failure)
1. Run `VectorReconciliationService.reconcileAll()` via admin endpoint or scheduled job.
2. Orphan vectors (in Milvus but not MySQL): safe to delete — they serve no citation purpose.
3. Missing vectors (in MySQL but not Milvus): re-index the affected documents.

---

## Index Versioning

Every indexing run produces a unique `index_version` (UUID). This is stored in:
- `document_index_job.index_version`
- `document_chunk.index_version`
- Milvus chunk metadata

Stale callbacks from superseded workers are rejected by matching `index_version`.

When the embedding model or dimension changes:
1. Set a new `embedding_version` (e.g., `v2`) in the Python config.
2. Re-index all documents — old chunks are automatically superseded.
3. The `embedding_model`, `embedding_dimension`, and `embedding_version` columns on `document_chunk` track provenance per chunk.

---

## Reconciliation Commands

### Check a single document
```bash
curl -H "X-Internal-Token: $PYTHON_AI_INTERNAL_TOKEN" \
  http://localhost:9000/api/chunks/{documentId}?page=1&size=100000
```

### Compare with MySQL
```sql
SELECT chunk_id, document_id, embedding_model, embedding_dimension
FROM document_chunk
WHERE document_id = {documentId}
ORDER BY chunk_index;
```

### Delete orphan vectors
```bash
# Via the vectorization API
curl -X DELETE -H "X-Internal-Token: $PYTHON_AI_INTERNAL_TOKEN" \
  http://localhost:9000/api/documents/{documentId}/chunks
```

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `VECTOR_STORE_MODE` | `lite` | `lite`（代码默认，仅本地裸跑/测试）或 `cluster`（Docker/生产，推荐） |
| `SERVER_ENV` | `development` | `production`/`staging`/`development` |
| `MILVUS_HOST` | `localhost` | Milvus standalone host |
| `MILVUS_PORT` | `19530` | Milvus standalone port |
| `MILVUS_LITE_PATH` | `./milvus_data.db` | 仅 `VECTOR_STORE_MODE=lite` 时的嵌入式 Lite 文件路径 |
| `MILVUS_ALLOW_COLLECTION_DROP` | `false` | Safety gate for destructive ops |
| `EMBEDDING_MODEL` | `unknown` | Current embedding model name |
| `EMBEDDING_DIMENSION` | `1024` | Vector dimension |

---

## Monitoring

- **Prometheus metrics**: `python_ai_vector_store_insert_total`, `python_ai_vector_store_search_total`
- **Alert rules**: `deploy/monitoring/alert_rules.yml` — vector store errors, high latency, reconciliation failures
- **Health check**: `GET /ready` on Python AI service (returns Milvus connection status)
