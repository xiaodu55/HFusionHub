# Milvus Migration Guide

> Moving from Milvus Lite (file-based) to Milvus Standalone (production).

## Current State

HFusionHub uses **Milvus Lite** — a file-based, embedded vector database.
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

**Recommended threshold**: Migrate when your total vectors exceed 500K or you need multi-instance access.

## Migration Steps

### 1. Start Milvus Standalone

```bash
# docker-compose.milvus.yml
services:
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
    volumes:
      - etcd-data:/etcd

  minio:
    image: minio/minio:latest
    command: minio server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio-data:/data

  milvus-standalone:
    image: milvusdb/milvus:v2.6.0
    command: milvus run standalone
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    ports:
      - "19530:19530"
    depends_on:
      - etcd
      - minio
```

### 2. Update Python Configuration

In `python-ai/.env`:

```bash
# Comment out Milvus Lite
# MILVUS_LITE_PATH=./milvus_data.db

# Add Milvus Standalone connection
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=hfusionhub_chunks
```

### 3. Update Vector Store Code

In `python-ai/app/core/vectorstore/milvus_store.py`, add a connection mode switch:

```python
from pymilvus import connections, Collection, utility

def get_milvus_client():
    if config.MILVUS_HOST:
        # Standalone mode
        connections.connect(
            alias="default",
            host=config.MILVUS_HOST,
            port=config.MILVUS_PORT,
        )
        return MilvusStandaloneStore()
    else:
        # Lite mode (current)
        return MilvusLiteStore(config.MILVUS_LITE_PATH)
```

### 4. Re-index Existing Documents

After switching to standalone, existing documents must be re-indexed:

```bash
# Via the Java backend API
curl -X POST http://localhost:8080/api/document/reindex-all \
  -H "satoken: <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"knowledge_base_id": 1}'
```

### 5. Verify Migration

```python
from pymilvus import Collection

col = Collection("hfusionhub_chunks")
print(f"Entities: {col.num_entities}")
print(f"Index: {col.index().params}")
```

## Rollback

To roll back to Milvus Lite:
1. Stop the Milvus standalone containers
2. Restore `MILVUS_LITE_PATH` in `.env`
3. Restart Python AI service
4. Documents indexed to standalone are not automatically available in Lite — re-index

## Production Checklist

- [ ] Milvus standalone runs on dedicated host/VM (not shared with app)
- [ ] MinIO uses persistent volumes (not tmpfs)
- [ ] etcd cluster has 3+ nodes for HA
- [ ] Network policy restricts Milvus port to Python AI service only
- [ ] TLS enabled for Milvus client connections
- [ ] Authentication enabled (`milvus.auth.enabled: true`)
- [ ] Regular backups of MinIO data and etcd snapshots
- [ ] Monitoring: Milvus metrics → Prometheus → Grafana
