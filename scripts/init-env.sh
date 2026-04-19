#!/usr/bin/env bash
# 生成/刷新 HFusionHub 全部本地环境配置文件（docker/.env、python-ai/.env、deploy/.env），
# 使用加密强度随机数自动填充密码与令牌。
#
# 用法:
#   bash scripts/init-env.sh            # 缺失时生成；已存在时跳过
#   bash scripts/init-env.sh --reset    # 强制重新生成全部口令
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESET=false
if [[ "${1:-}" == "--reset" ]]; then RESET=true; fi

rand() { # rand <len> — 加密强度随机字母数字串（去除易混淆字符）
  local len="${1:-24}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 48 | tr -dc 'A-HJ-NP-Za-kmnp-z2-9' | head -c "$len"
  else
    tr -dc 'A-HJ-NP-Za-kmnp-z2-9' </dev/urandom | head -c "$len"
  fi
  echo
}

set_key() { # set_key <file> <key> <value> — 存在则替换，否则追加
  local file="$1" key="$2" value="$3"
  if grep -qE "^${key}=" "$file"; then
    sed -i.bak -E "s|^${key}=.*|${key}=${value}|" "$file" && rm -f "$file.bak"
  else
    printf '\n%s=%s\n' "$key" "$value" >>"$file"
  fi
}

echo "==> 生成 HFusionHub 环境配置（仓库根: ${REPO_ROOT}）"

INTERNAL_TOKEN="$(rand 32)"
CALLBACK_SECRET="$(rand 32)"
ADMIN_PASS="$(rand 16)"

# 1) docker/.env（基础设施）
if [[ -f "$REPO_ROOT/docker/.env" && "$RESET" != true ]]; then
  echo "  [skip] docker/.env 已存在（使用 --reset 重新生成）"
else
  [[ -f "$REPO_ROOT/docker/.env" ]] || cp "$REPO_ROOT/docker/.env.example" "$REPO_ROOT/docker/.env"
  set_key "$REPO_ROOT/docker/.env" MYSQL_ROOT_PASSWORD "$(rand 20)"
  set_key "$REPO_ROOT/docker/.env" MYSQL_PASSWORD "$(rand 20)"
  set_key "$REPO_ROOT/docker/.env" REDIS_PASSWORD "$(rand 20)"
  set_key "$REPO_ROOT/docker/.env" MINIO_ROOT_PASSWORD "$(rand 20)"
  set_key "$REPO_ROOT/docker/.env" PLUGIN_RUNNER_TOKEN "$(rand 32)"
  set_key "$REPO_ROOT/docker/.env" ADMIN_PASSWORD "$ADMIN_PASS"
  set_key "$REPO_ROOT/docker/.env" PYTHON_AI_INTERNAL_TOKEN "$INTERNAL_TOKEN"
  set_key "$REPO_ROOT/docker/.env" CALLBACK_SECRET "$CALLBACK_SECRET"
  echo "  [ok] docker/.env 已更新为随机强口令"
fi

# 2) python-ai/.env（更新共享令牌；其余配置保持不变）
if [[ -f "$REPO_ROOT/python-ai/.env" && "$RESET" != true ]]; then
  echo "  [skip] python-ai/.env 已存在（使用 --reset 重新生成）"
else
  [[ -f "$REPO_ROOT/python-ai/.env" ]] || cp "$REPO_ROOT/python-ai/.env.example" "$REPO_ROOT/python-ai/.env"
  set_key "$REPO_ROOT/python-ai/.env" PYTHON_AI_INTERNAL_TOKEN "$INTERNAL_TOKEN"
  set_key "$REPO_ROOT/python-ai/.env" CALLBACK_SECRET "$CALLBACK_SECRET"
  echo "  [ok] python-ai/.env 令牌与 docker/.env 保持一致"
fi

# 3) deploy/.env（生产部署）
if [[ -f "$REPO_ROOT/deploy/.env" && "$RESET" != true ]]; then
  echo "  [skip] deploy/.env 已存在（使用 --reset 重新生成）"
else
  [[ -f "$REPO_ROOT/deploy/.env" ]] || cp "$REPO_ROOT/deploy/.env.example" "$REPO_ROOT/deploy/.env"
  set_key "$REPO_ROOT/deploy/.env" MYSQL_ROOT_PASSWORD "$(rand 20)"
  set_key "$REPO_ROOT/deploy/.env" MYSQL_PASSWORD "$(rand 20)"
  set_key "$REPO_ROOT/deploy/.env" PYTHON_AI_INTERNAL_TOKEN "$INTERNAL_TOKEN"
  set_key "$REPO_ROOT/deploy/.env" CALLBACK_SECRET "$CALLBACK_SECRET"
  set_key "$REPO_ROOT/deploy/.env" ADMIN_PASSWORD "$ADMIN_PASS"
  set_key "$REPO_ROOT/deploy/.env" PLUGIN_RUNNER_TOKEN "$(rand 32)"
  echo "  [ok] deploy/.env 已生成"
fi

echo ""
echo "==> 完成。还需手动填写以下内容（脚本无法猜测）："
echo "  1. python-ai/.env 与 deploy/.env 中的 DEEPSEEK_API_KEY（旧 Key 若曾泄露请先轮换）"
echo "  2. deploy/.env 中的 PLUGIN_RUNNER_DOCKER_HOST 与 3 个 Runner TLS 证书路径"
echo "     （先运行 bash scripts/generate-runner-tls.sh deploy/runner-tls）"
echo "  3. 管理员账号：admin / ${ADMIN_PASS}（由 ADMIN_PASSWORD 决定）"
echo ""
echo "下一步：bash scripts/setup.sh 一键启动（--fullstack 全部容器化）。"
