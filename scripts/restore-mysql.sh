#!/usr/bin/env bash
# restore-mysql.sh — HFusionHub MySQL 备份恢复 / 恢复演练（TODO.md P0 #5 / PRODUCTION_OPS 第 8 节）
#
# 用法:
#   ./scripts/restore-mysql.sh backups/mysql/hfusionhub_20260903_023000.sql.gz --yes
#       # 恢复到生产栈（deploy/docker-compose.prod.yml）——会覆盖库内现有数据
#   ./scripts/restore-mysql.sh <dump.sql.gz> --yes --dev
#       # 恢复到开发栈（docker/docker-compose.yml）——恢复演练推荐路径
#
# 行为:
#   1. 校验 dump 文件（gzip 完整性 + MySQL dump 头）
#   2. 重建 hfusionhub 库（DROP + CREATE，root 身份，容器内环境读旧密码）
#   3. 灌入 dump（mysqldump 自带 DROP TABLE IF EXISTS，双保险）
#   4. 恢复后核验：表数量 + 关键表行数 + Flyway 历史存在性
#
# 警告:
#   - 恢复覆盖目标库全部数据！生产执行前务必先在测试环境演练。
#   - 密码从容器内环境读取（docker compose exec），不落盘、不进命令行参数。
#
# 演练闭环建议（对应 PRODUCTION_OPS 第 8 节）:
#   ./scripts/backup-mysql.sh                         # 1. 备份
#   ./scripts/restore-mysql.sh <刚生成的dump> --yes --dev   # 2. 恢复（演练环境）
#   ./scripts/smoke-test.ps1                          # 3. 全栈冒烟确认业务可用

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

DUMP=""
ASSUME_YES=0
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.prod.yml"

for arg in "$@"; do
  case "$arg" in
    --yes) ASSUME_YES=1 ;;
    --dev) COMPOSE_FILE="$REPO_ROOT/docker/docker-compose.yml" ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) DUMP="$arg" ;;
  esac
done

if [[ -z "$DUMP" || ! -f "$DUMP" ]]; then
  echo "错误: 请提供有效的 dump 文件路径（.sql.gz）。用法见 $0 --help" >&2
  exit 1
fi

echo "── 恢复目标: $COMPOSE_FILE"
echo "── dump 文件: $DUMP ($(du -h "$DUMP" | cut -f1))"

# 1. dump 完整性校验
if ! gzip -t "$DUMP"; then
  echo "错误: gzip 校验失败，dump 文件损坏" >&2; exit 1
fi
# 注意: 不能写 `zcat | head | grep -q` —— pipefail 下 grep -q 提前退出会让
# zcat 吃 SIGPIPE(141)，误判校验失败；先截取头部字节再匹配。
DUMP_HEAD="$(zcat "$DUMP" 2>/dev/null | head -c 4096 || true)"
if ! printf '%s\n' "$DUMP_HEAD" | grep -q "MySQL dump"; then
  echo "错误: 文件不是 MySQL dump（缺少 dump 头）" >&2; exit 1
fi
echo "── dump 校验通过"

# 2. 危险操作确认
if [[ $ASSUME_YES -ne 1 ]]; then
  read -r -p "即将 DROP 并重建 hfusionhub 库，覆盖全部现有数据。输入 yes 继续: " CONFIRM
  [[ "$CONFIRM" == "yes" ]] || { echo "已取消"; exit 1; }
fi

# 3. 重建库（root 密码从容器环境读取）
echo "[$(date '+%F %T')] 重建数据库 hfusionhub ..."
docker compose -f "$COMPOSE_FILE" exec -T mysql8 sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS hfusionhub; CREATE DATABASE hfusionhub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"' \
  2> >(grep -v "Using a password" >&2)

# 4. 灌入 dump
echo "[$(date '+%F %T')] 灌入 dump ..."
gunzip -c "$DUMP" | docker compose -f "$COMPOSE_FILE" exec -T mysql8 sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hfusionhub' \
  2> >(grep -v "Using a password" >&2)

# 5. 恢复后核验（SQL 经 stdin 传入，避开多层引号嵌套）
echo "[$(date '+%F %T')] 核验恢复结果 ..."
MYSQL_ROOT() {
  docker compose -f "$COMPOSE_FILE" exec -T mysql8 sh -c \
    'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N hfusionhub' 2>/dev/null
}
TABLES=$(printf "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='hfusionhub'\n" \
  | MYSQL_ROOT | tail -1 || true)
if [[ -z "${TABLES:-}" || "${TABLES:-0}" -eq 0 ]]; then
  echo "错误: 恢复后 0 张表，核验失败" >&2; exit 1
fi
echo "  表数量: $TABLES"

KEY_TABLES="sys_user knowledge_base document conversation message flyway_schema_history"
FAIL=0
for t in $KEY_TABLES; do
  ROWS=$(printf "SELECT COUNT(*) FROM \`%s\`\n" "$t" | MYSQL_ROOT | tail -1 || true)
  if [[ -z "${ROWS:-}" ]]; then
    echo "  [!] 关键表 $t 不存在或查询失败"; FAIL=1
  else
    echo "  $t: $ROWS 行"
  fi
done
[[ $FAIL -eq 1 ]] && exit 1

echo "[$(date '+%F %T')] 恢复完成且核验通过。建议运行全栈冒烟确认业务可用（scripts/smoke-test.ps1）"
