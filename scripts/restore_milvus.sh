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
VOLUME_NAME="hfusionhub_milvus-data"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: Backup file not found: $BACKUP_FILE"
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
