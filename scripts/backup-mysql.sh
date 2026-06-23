#!/usr/bin/env bash
# backup-mysql.sh — HFusionHub 生产 MySQL 每日备份（TODO.md P0 #5 / PRODUCTION_OPS 第 8 节）
#
# 用法（在 deploy/ 目录的生产 compose 下运行）:
#   ./scripts/backup-mysql.sh                        # 备份到 ./backups/mysql/
#   ./scripts/backup-mysql.sh -d /var/backups/hfhub  # 指定目录
#   BACKUP_KEEP=14 ./scripts/backup-mysql.sh         # 保留 14 天
#
# crontab 每日 02:30 示例（宿主机）:
#   30 2 * * * cd /path/to/HFusionHub1 && ./scripts/backup-mysql.sh >> /var/log/hfhub-backup.log 2>&1
#
# 说明:
#   - 密码从容器内环境读取（docker compose exec），不落盘、不进命令行参数。
#   - 单表事务一致性 dump（--single-transaction），InnoDB 下不锁表。
#   - 恢复演练: gunzip -c <dump>.sql.gz | docker compose -f deploy/docker-compose.prod.yml \
#       exec -T mysql8 mysql -uhfusionhub -p"$MYSQL_PASSWORD" hfusionhub
#     （恢复前先在测试环境演练，PRODUCTION_OPS.md 第 8 节）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups/mysql}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%F %T')] 开始 MySQL 备份 -> $BACKUP_DIR/hfusionhub_$STAMP.sql.gz"

docker compose -f "$COMPOSE_FILE" exec -T mysql8 sh -c \
  'exec mysqldump -uhfusionhub -p"$MYSQL_PASSWORD" --single-transaction --routines --triggers hfusionhub' \
  | gzip > "$BACKUP_DIR/hfusionhub_$STAMP.sql.gz"

SIZE=$(du -h "$BACKUP_DIR/hfusionhub_$STAMP.sql.gz" | cut -f1)
echo "[$(date '+%F %T')] 备份完成: hfusionhub_$STAMP.sql.gz ($SIZE)"

# 验证 dump 非空且以 MySQL dump 头开始
if ! gzip -t "$BACKUP_DIR/hfusionhub_$STAMP.sql.gz" || \
   ! zcat "$BACKUP_DIR/hfusionhub_$STAMP.sql.gz" | head -5 | grep -q "MySQL dump"; then
  echo "[$(date '+%F %T')] 错误: 备份文件校验失败" >&2
  rm -f "$BACKUP_DIR/hfusionhub_$STAMP.sql.gz"
  exit 1
fi

# 清理旧备份
OLD_COUNT=$(find "$BACKUP_DIR" -name "hfusionhub_*.sql.gz" -mtime +"$BACKUP_KEEP" | wc -l)
find "$BACKUP_DIR" -name "hfusionhub_*.sql.gz" -mtime +"$BACKUP_KEEP" -delete
echo "[$(date '+%F %T')] 清理 $OLD_COUNT 个超过 ${BACKUP_KEEP} 天的旧备份"

# 提醒: Milvus 向量卷快照见 scripts/backup_milvus.sh / restore_milvus.sh
echo "[$(date '+%F %T')] 完成。Milvus 快照请另行运行 scripts/backup_milvus.sh"
