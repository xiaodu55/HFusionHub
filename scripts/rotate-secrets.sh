#!/usr/bin/env bash
# ═════════════════════════════════════════════════════════════════════════
# rotate-secrets.sh — 生产上线前默认密码/令牌轮换助手（R15-26）
#
# 作用：生成强随机密钥并打印「需要同步更新的配置位置清单」。默认只打印
# 不落盘——避免把新密钥写进 shell 历史或日志；确认后由操作者手动更新
# docker/.env / deploy/.env 并按提示的顺序重启栈。
#
# 覆盖密钥（对应 TODO.md P0-1 / docs/PRODUCTION_OPS.md §0）：
#   MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD      MySQL root 与业务账户
#   REDIS_PASSWORD                            Redis（须与 Java spring.data.redis.password 一致）
#   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD     MinIO（与 Java minio.access-key/secret-key 一致）
#   PLUGIN_RUNNER_TOKEN                       Java ↔ plugin-runner（两侧一致）
#   PYTHON_AI_INTERNAL_TOKEN                  Java ↔ Python（两侧一致）
#   CALLBACK_SECRET                           Python → Java 回调 HMAC（两侧一致）
#   MODEL_CREDENTIAL_ENCRYPTION_KEY           用户模型凭据加密（独立生成，勿复用内部令牌）
#   ADMIN_PASSWORD                            平台管理员初始密码
#
# 用法：
#   ./scripts/rotate-secrets.sh              # 打印全部新密钥与更新指引
#   ./scripts/rotate-secrets.sh --check      # 只检查 docker/.env 中的弱默认值
# ═════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/docker/.env"

gen() { openssl rand -base64 30 | tr -d '/+=' | head -c 40; }

WEAK_PATTERNS='^(minioadmin|plugin-runner-secret|123456|password|admin|test|change-me)'

check_env() {
  echo "── 检查 $ENV_FILE 中的弱默认值 ──"
  local found=0
  while IFS= read -r line; do
    case "$line" in
      \#*|'') continue ;;
    esac
    key="${line%%=*}"; val="${line#*=}"
    if echo "$val" | grep -qiE "$WEAK_PATTERNS"; then
      echo "  [!] $key 使用弱默认值，必须轮换"
      found=1
    fi
  done < "$ENV_FILE"
  [[ $found -eq 0 ]] && echo "  [ok] 未发现弱默认值"
  if ! grep -q '^MODEL_CREDENTIAL_ENCRYPTION_KEY=.' "$ENV_FILE"; then
    echo "  [!] MODEL_CREDENTIAL_ENCRYPTION_KEY 未配置——保存/读取用户模型凭据会 fail-fast"
  fi
}

if [[ "${1:-}" == "--check" ]]; then
  check_env
  exit 0
fi

echo "══ 新密钥（手动更新后按下方顺序重启）══"
declare -A SECRETS=(
  [MYSQL_ROOT_PASSWORD]=$(gen)
  [MYSQL_PASSWORD]=$(gen)
  [REDIS_PASSWORD]=$(gen)
  [MINIO_ROOT_USER]=hfusionhub$(gen | tr 'A-Z' 'a-z' | head -c 8)
  [MINIO_ROOT_PASSWORD]=$(gen)
  [PLUGIN_RUNNER_TOKEN]=$(gen)
  [PYTHON_AI_INTERNAL_TOKEN]=$(gen)
  [CALLBACK_SECRET]=$(gen)
  [MODEL_CREDENTIAL_ENCRYPTION_KEY]=$(gen)
  [ADMIN_PASSWORD]=$(gen)
)
for k in "${!SECRETS[@]}"; do
  echo "  $k=${SECRETS[$k]}"
done

cat <<'EOF'

══ 同步位置（两侧必须一致，否则启动 NOAUTH / 403）══
  1. docker/.env（dev）与 deploy/.env（prod/staging）
  2. MySQL 业务数据无需重加密；MinIO 凭据变更后旧 bucket 所有权不变
  3. MODEL_CREDENTIAL_ENCRYPTION_KEY 变更将使**已保存的用户模型凭据不可解密**
     （需用户重新录入）——请安排公告后执行
  4. 重启顺序：
        docker compose down
        docker compose up -d mysql8 redis7 minio dind
        docker compose up -d plugin-runner   # 等待 healthy
        docker compose --profile fullstack up -d
  5. 完成后运行 scripts/smoke-test.ps1（期望 47 PASS / 0 FAIL）

══ 其余上线阻断项（docs/PRODUCTION_OPS.md §0）══
  - HTTPS：参考 deploy/nginx-https.conf.example + certbot
  - CORS：设置 app.cors.allow-any-origin=false 并配置 app.cors.allowed-origins
  - Swagger：生产通过环境变量关闭（SPRINGDOC_API_DOCS_ENABLED=false）
  - 备份：scripts/backup-data.ps1（MySQL）+ scripts/backup_milvus.sh（Milvus）加入 cron/计划任务
  - 告警：启动 deploy/docker-compose.monitoring.yml 并配置 Alertmanager 通知渠道
EOF
