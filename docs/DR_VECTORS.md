# Disaster Recovery Runbook — Vector Store Migration

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
```bash
# Stop Milvus briefly for consistent snapshot
docker compose -f deploy/docker-compose.prod.yml stop milvus

# Snapshot the data volume
docker run --rm -v hfusionhub_milvus-data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/milvus_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Restart Milvus
docker compose -f deploy/docker-compose.prod.yml start milvus
```

### Cluster mode: co-store JSON is not used
Production / staging run in `VECTOR_STORE_MODE=cluster`. BM25 and citations
read their scoped corpus directly from Milvus via `all_chunks()`; there is no
per-pod `chunks_store.json`, so no separate co-store backup is required.

### Lite dev mode: co-store JSON only
The `chunks_store.json` local co-store exists only in `VECTOR_STORE_MODE=lite`
for local development and tests. If you run Lite locally, it lives in the
`python-data` volume and may be copied as:
```bash
docker run --rm -v hfusionhub_python-data:/data -v $(pwd)/backups:/backup \
  alpine cp /data/chunks_store.json /backup/chunks_store_$(date +%Y%m%d_%H%M%S).json
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
| `VECTOR_STORE_MODE` | `lite` | `lite` (dev) or `cluster` (prod) |
| `SERVER_ENV` | `development` | `production`/`staging`/`development` |
| `MILVUS_HOST` | `localhost` | Milvus standalone host |
| `MILVUS_PORT` | `19530` | Milvus standalone port |
| `MILVUS_LITE_PATH` | `./milvus_data.db` | Embedded Lite file path |
| `MILVUS_ALLOW_COLLECTION_DROP` | `false` | Safety gate for destructive ops |
| `EMBEDDING_MODEL` | `unknown` | Current embedding model name |
| `EMBEDDING_DIMENSION` | `1024` | Vector dimension |

---

## Monitoring

- **Prometheus metrics**: `python_ai_vector_store_insert_total`, `python_ai_vector_store_search_total`
- **Alert rules**: `deploy/monitoring/alert_rules.yml` — vector store errors, high latency, reconciliation failures
- **Health check**: `GET /ready` on Python AI service (returns Milvus connection status)
