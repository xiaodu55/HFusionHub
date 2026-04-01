#!/usr/bin/env bash
# backup_milvus.sh — Snapshot Milvus data volume for disaster recovery.
#
# Usage:
#   ./scripts/backup_milvus.sh [backup_dir]
#
# Prerequisites:
#   - Docker Compose with Milvus service running
#   - write access to the backup directory

set -euo pipefail

BACKUP_DIR="${1:-$(pwd)/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
COMPOSE_FILE="deploy/docker-compose.prod.yml"
VOLUME_NAME="hfusionhub_milvus-data"

mkdir -p "$BACKUP_DIR"

echo "[backup] Stopping Milvus for consistent snapshot..."
docker compose -f "$COMPOSE_FILE" stop milvus

echo "[backup] Snapshotting volume ${VOLUME_NAME}..."
docker run --rm \
  -v "${VOLUME_NAME}:/data:ro" \
  -v "${BACKUP_DIR}:/backup" \
  alpine tar czf "/backup/milvus_${TIMESTAMP}.tar.gz" -C /data .

echo "[backup] Starting Milvus..."
docker compose -f "$COMPOSE_FILE" start milvus

echo "[backup] Backup saved: ${BACKUP_DIR}/milvus_${TIMESTAMP}.tar.gz"
echo "[backup] Size: $(du -h "${BACKUP_DIR}/milvus_${TIMESTAMP}.tar.gz" | cut -f1)"
