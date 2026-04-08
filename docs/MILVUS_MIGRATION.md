# Milvus Migration Guide

> Moving from Milvus Lite (file-based, dev) to Milvus Standalone (production).

## Current State

HFusionHub uses **Milvus Lite** for development — a file-based, embedded vector database.
- Storage: `python-ai/milvus_data.db` (local file)
- Index: `IVF_FLAT`, 1024-dim `FLOAT_VECTOR`, `COSINE` metric
- Suitable for: development, single-user, <100K vectors

## When to Migrate

| Milvus Lite Limit | Standalone Benefit |
|-------------------|-------------------|
| Single-process access | Multi-client concurrent access |
| File-based, no replication | Distributed, replicated storage |
| Memory-mapped file I/O | Optimized vector index in memory |
| No auth / TLS | RBAC, TLS encryption |
| <1M vectors practical limit | 10M+ vectors with partitioning |

**Recommended threshold**: Migrate when total vectors exceed 500K or you need multi-instance access.

## Production Setup (Already Configured)

The production Docker Compose (`deploy/docker-compose.prod.yml`) already includes:

```yaml
milvus:
  image: milvusdb/milvus:v2.4.0
  command: ["milvus", "run", "standalone"]
  environment:
    ETCD_USE_EMBED: "true"
    COMMON_STORAGETYPE: local
  ports:
    - "127.0.0.1:19530:19530"
    - "127.0.0.1:9091:9091"
```

## Migration Steps

### 1. Switch Vector Store Mode

In `python-ai/.env` (or `deploy/.env` for production):

```bash
# Enable cluster mode
VECTOR_STORE_MODE=cluster
SERVER_ENV=production

# Point to Milvus standalone
MILVUS_HOST=milvus        # service name in docker-compose
MILVUS_PORT=19530
MILVUS_COLLECTION=hfusionhub_chunks

# Comment out Milvus Lite
# MILVUS_LITE_PATH=./milvus_data.db
```

### 2. Start Production Stack

```bash
docker compose -f deploy/docker-compose.prod.yml up -d
```

This starts Milvus standalone alongside all other services with the correct `VECTOR_STORE_MODE=cluster` already configured.

### 3. Re-index Existing Documents

After switching, existing documents must be re-indexed via the vectorization API:

```bash
# Re-index a specific document
curl -X POST http://localhost:8080/api/vectorize/{documentId} \
  -H "satoken: <your-token>" \
  -H "Content-Type: application/json"

# Or sync all documents in a knowledge base
curl -X POST http://localhost:8080/api/vectorize/sync-all \
  -H "satoken: <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"knowledge_base_id": 1}'
```

### 4. Verify Migration

```python
from pymilvus import Collection

col = Collection("hfusionhub_chunks")
print(f"Entities: {col.num_entities}")
print(f"Index: {col.index().params}")
```

## Rollback

To roll back to Milvus Lite:
1. Set `VECTOR_STORE_MODE=lite` (or unset it)
2. Restore `MILVUS_LITE_PATH` in `.env`
3. Restart Python AI service
4. Documents indexed to standalone are not automatically available in Lite — re-index needed

## Production Checklist

- [ ] Milvus standalone runs on dedicated host/VM (not shared with app)
- [ ] Persistent volumes for Milvus data
- [ ] Network policy restricts Milvus port to Python AI service only
- [ ] TLS enabled for Milvus client connections
- [ ] Authentication enabled (`milvus.auth.enabled: true`)
- [ ] Regular backups of Milvus data
- [ ] Monitoring: Milvus metrics → Prometheus → Grafana
