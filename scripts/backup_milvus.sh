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

# Docker Compose 默认项目名 = compose 文件所在目录名（可用 COMPOSE_PROJECT_NAME 覆盖），
# 数据卷实际名为 "<project>_milvus-data"。按同样的规则推导，避免硬编码错卷。
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$(dirname "$COMPOSE_FILE")")}"
VOLUME_NAME="${COMPOSE_PROJECT_NAME}_milvus-data"

if ! docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
  echo "[backup] ERROR: volume '$VOLUME_NAME' not found." >&2
  echo "[backup]   Run: docker volume ls | grep milvus-data  (dev stack: docker_milvus-data)" >&2
  echo "[backup]   Or set COMPOSE_PROJECT_NAME to match your stack." >&2
  exit 1
fi

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
