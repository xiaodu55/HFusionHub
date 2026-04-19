#!/usr/bin/env bash
# restore_milvus.sh — Restore Milvus data from a backup snapshot.
#
# Usage:
#   ./scripts/restore_milvus.sh <backup_file.tar.gz>
#
# WARNING: This will REPLACE the current Milvus data volume.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup_file.tar.gz>"
  exit 1
fi

BACKUP_FILE="$1"
COMPOSE_FILE="deploy/docker-compose.prod.yml"

# Docker Compose 默认项目名 = compose 文件所在目录名（可用 COMPOSE_PROJECT_NAME 覆盖），
# 数据卷实际名为 "<project>_milvus-data"。按同样的规则推导，避免硬编码错卷。
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$(dirname "$COMPOSE_FILE")")}"
VOLUME_NAME="${COMPOSE_PROJECT_NAME}_milvus-data"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: Backup file not found: $BACKUP_FILE"
  exit 1
fi

if ! docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
  echo "[restore] ERROR: volume '$VOLUME_NAME' not found." >&2
  echo "[restore]   Run: docker volume ls | grep milvus-data  (dev stack: docker_milvus-data)" >&2
  echo "[restore]   Or set COMPOSE_PROJECT_NAME to match your stack." >&2
  exit 1
fi

echo "[restore] Stopping Milvus..."
docker compose -f "$COMPOSE_FILE" stop milvus

echo "[restore] Clearing existing volume data..."
docker run --rm -v "${VOLUME_NAME}:/data" alpine rm -rf /data/*

echo "[restore] Extracting backup to volume..."
docker run --rm \
  -v "${VOLUME_NAME}:/data" \
  -v "$(realpath "$BACKUP_FILE"):/backup.tar.gz:ro" \
  alpine tar xzf /backup.tar.gz -C /data

echo "[restore] Starting Milvus..."
docker compose -f "$COMPOSE_FILE" start milvus

echo "[restore] Waiting for Milvus health check..."
sleep 10

echo "[restore] Verifying collection..."
docker compose -f "$COMPOSE_FILE" exec milvus \
  curl -sf http://localhost:9091/healthz && echo " OK" || echo " WARNING: health check failed"

echo "[restore] Restore complete from: $BACKUP_FILE"
