#!/usr/bin/env bash
# rotate-db-password.sh — 把 .env 中已更新的 MySQL 密码"落实"到数据库账户
# （TODO.md P0 #1：数据库密码属卷内状态，仅改 .env 不会生效，须 ALTER USER）
#
# 背景:
#   rotate-secrets.sh 生成新密码并写入 docker/.env / deploy/.env 后，运行中的
#   mysql8 容器内账户仍是旧密码；Java/Python 容器要等栈重启才读到新密码。
#   本脚本用【容器内现有（旧）root 密码】登录，把 root 与 hfusionhub 账户
#   ALTER 成 .env 中的【新】值；随后 `docker compose down && up -d` 重启栈，
#   全部服务以新密码互通。
#
# 用法:
#   ./scripts/rotate-db-password.sh --apply --yes        # 生产栈（deploy/.env）
#   ./scripts/rotate-db-password.sh --apply --yes --dev  # 开发栈（docker/.env）
#   ./scripts/rotate-db-password.sh --check              # 复核 .env 密码能否登录（重启后复核）
#   ./scripts/rotate-db-password.sh --check --dev
#
# 安全性:
#   - 新密码经 stdin 传入容器内 mysql，不进 argv、不写日志；
#   - 含单引号/反斜杠/美元符的密码会被拒绝（rotate-secrets.sh 生成值均为字母数字）；
#   - .env 值与容器当前值一致时跳过（无待生效轮换）。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

MODE="${1:-}"
ASSUME_YES=0
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.prod.yml"
ENV_FILE="$REPO_ROOT/deploy/.env"

for arg in "$@"; do
  case "$arg" in
    --apply|--check) MODE="$arg" ;;
    --yes) ASSUME_YES=1 ;;
    --dev)
      COMPOSE_FILE="$REPO_ROOT/docker/docker-compose.yml"
      ENV_FILE="$REPO_ROOT/docker/.env" ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
  esac
done

[[ "$MODE" == "--apply" || "$MODE" == "--check" ]] || { echo "用法: $0 --apply|--check [--yes] [--dev]" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "错误: 未找到 $ENV_FILE" >&2; exit 1; }

env_val() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }
NEW_ROOT="$(env_val MYSQL_ROOT_PASSWORD)"
NEW_APP="$(env_val MYSQL_PASSWORD)"
[[ -n "$NEW_ROOT" && -n "$NEW_APP" ]] || { echo "错误: $ENV_FILE 缺少 MYSQL_ROOT_PASSWORD/MYSQL_PASSWORD" >&2; exit 1; }
for v in "$NEW_ROOT" "$NEW_APP"; do
  if echo "$v" | grep -q "['\\\\\$]"; then
    echo "错误: 密码含 ' \\ \$ 字符，无法安全经 SQL 传递；请换用字母数字密码（rotate-secrets.sh 生成值即满足）" >&2
    exit 1
  fi
done

# 容器内当前值（旧密码）——用于判断是否有待生效轮换
CUR_ROOT="$(docker compose -f "$COMPOSE_FILE" exec -T mysql8 printenv MYSQL_ROOT_PASSWORD)"
CUR_APP="$(docker compose -f "$COMPOSE_FILE" exec -T mysql8 printenv MYSQL_PASSWORD)"

if [[ "$MODE" == "--check" ]]; then
  echo "── 用 $ENV_FILE 中的新密码尝试登录（栈重启后复核）"
  if docker compose -f "$COMPOSE_FILE" exec -T -e MYSQL_PWD="$NEW_APP" mysql8 \
      sh -c 'exec mysql -uhfusionhub -N -e "SELECT 1"' >/dev/null 2>&1; then
    echo "  [ok] hfusionhub 新密码可登录"
  else
    echo "  [!] hfusionhub 新密码登录失败（若尚未 --apply，先执行 apply）" >&2
    exit 1
  fi
  if docker compose -f "$COMPOSE_FILE" exec -T -e MYSQL_PWD="$NEW_ROOT" mysql8 \
      sh -c 'exec mysql -uroot -N -e "SELECT 1"' >/dev/null 2>&1; then
    echo "  [ok] root 新密码可登录"
  else
    echo "  [!] root 新密码登录失败（若尚未 --apply，先执行 apply）" >&2
    exit 1
  fi
  exit 0
fi

# --apply
if [[ "$NEW_ROOT" == "$CUR_ROOT" && "$NEW_APP" == "$CUR_APP" ]]; then
  echo "── .env 与容器内密码一致，无待生效轮换，跳过"
  exit 0
fi

if [[ $ASSUME_YES -ne 1 ]]; then
  read -r -p "即将 ALTER root@'%'、root@'localhost'、hfusionhub@'%' 为 .env 新密码。输入 yes 继续: " CONFIRM
  [[ "$CONFIRM" == "yes" ]] || { echo "已取消"; exit 1; }
fi

SQL="ALTER USER 'root'@'%' IDENTIFIED BY '$NEW_ROOT';"
SQL="$SQL ALTER USER 'root'@'localhost' IDENTIFIED BY '$NEW_ROOT';"
SQL="$SQL ALTER USER 'hfusionhub'@'%' IDENTIFIED BY '$NEW_APP';"
SQL="$SQL FLUSH PRIVILEGES;"

echo "[$(date '+%F %T')] 落实新密码（经 stdin 传入，不进 argv/日志）..."
printf '%s\n' "$SQL" | docker compose -f "$COMPOSE_FILE" exec -T mysql8 sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' 2> >(grep -v "Using a password" >&2)

echo "[$(date '+%F %T')] 完成。下一步:"
echo "  1) docker compose -f $COMPOSE_FILE down && docker compose -f $COMPOSE_FILE up -d   # 重启栈使 Java/Python 读新密码"
echo "  2) 重启后复核: ./scripts/rotate-db-password.sh --check （开发栈加 --dev）"
