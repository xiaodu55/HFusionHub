#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# HFusionHub — Staging 部署演练（Docker Compose）
#
# 目标：用 deploy/docker-compose.prod.yml 在隔离环境拉全链路，验证
#   Java / Python / Milvus / plugin-runner / frontend 全部健康。
#
# 设计要点：
#   * 真实 .env：优先用 deploy/.env（存在则复用），否则从 .env.example 复制，
#     …… 会为缺失的必填密钥自动生成随机值并回写。
#   * Runner TLS：若 deploy/runner-tls/{ca,cert,key}.pem 不存在则调用
#     scripts/generate-runner-tls.sh 生成。
#   * 健康校验：一律用 `docker compose ps --format` 读取 Go 模板
#     {{.Service}}\t{{.Name}}\t{{.Health}}，按 Compose 服务名精确匹配，
#     绝不手拼容器名（避免 hfusionhub-mysql8 之类误判）。
#   * 隔离 Docker Engine：生产上 runner 连独立 TLS 引擎。本机演练可选用
#     docker:dind 作为演练引擎；连不上/不可用时显式标注 runner 预期 503。
#   * --down 默认只停不删卷；加 --prune-volumes 才删除数据卷。
#
# 用法：
#   bash scripts/staging-rehearsal.sh                  # 起服务 + 健康校验
#   bash scripts/staging-rehearsal.sh --no-dind      # 不起 dind，runner 预期 503
#   bash scripts/staging-rehearsal.sh --down         # 停止演练（保留数据卷）
#   bash scripts/staging-rehearsal.sh --down --prune-volumes   # 停止并删卷
#
# 退出码：0=全部服务 healthy(含 runner 连上引擎)；
#         3=应用全链 healthy 但 runner 未连引擎(预期 503)；
#         1=存在非 runner 服务未 healthy。
#
# Windows 本机若无法运行 bash，请用 scripts/staging-rehearsal.ps1 等价脚本。
# -----------------------------------------------------------------------------
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="deploy/docker-compose.prod.yml"
ENV_FILE="$ROOT/deploy/.env"
TLS_DIR="$ROOT/deploy/runner-tls"
ACTION="up"
PRUNE_VOLUMES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --down) ACTION="down" ;;
    --no-dind) USE_DIND=0 ;;
    --prune-volumes) PRUNE_VOLUMES=1 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

need() { command -v "$1" >/dev/null 2>&1 || { echo "::error:: missing: $1"; exit 2; }; }
need docker
docker compose version >/dev/null 2>&1 || { echo "::error:: docker compose 插件不可用"; exit 2; }

# ── stop ────────────────────────────────────────────────────────────────
if [[ "$ACTION" == "down" ]]; then
  extra_rm=""
  [[ "$PRUNE_VOLUMES" == "1" ]] && extra_rm="-v"
  (cd "$ROOT" && docker compose -f "$COMPOSE" down $extra_rm --remove-orphans)
  DIND_NAME="hfusionhub-rehearsal-dind"
  if docker ps -a --format '{{.Names}}' | grep -qx "$DIND_NAME"; then
    docker rm -f "$DIND_NAME" >/dev/null 2>&1 && echo "演练 dind 引擎已移除"
  fi
  echo "staging 环境已停止（数据卷默认保留；需删除请加 --prune-volumes）。"
  exit 0
fi

need bash

# ── 1. .env ─────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/deploy/.env.example" "$ENV_FILE"
  echo "已从 .env.example 复制 deploy/.env（请确认密钥已替换）"
fi

random_hex() { docker run --rm alpine:3.20 sh -c "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'" 2>/dev/null; }
ensure_key() {
  local var="$1"
  if ! grep -qE "^${var}=[^ ]+" "$ENV_FILE"; then
    echo "${var}=$(random_hex)" >> "$ENV_FILE"
    echo "已为 ${var} 写入随机占位值"
  fi
}
for k in MYSQL_ROOT_PASSWORD MYSQL_PASSWORD PYTHON_AI_INTERNAL_TOKEN \
         CALLBACK_SECRET ADMIN_PASSWORD PLUGIN_RUNNER_TOKEN DEEPSEEK_API_KEY; do
  ensure_key "$k"
done

# ── 2. Runner TLS 证书 ──────────────────────────────────────────────────
if [[ ! -f "$TLS_DIR/ca.pem" || ! -f "$TLS_DIR/cert.pem" || ! -f "$TLS_DIR/key.pem" ]]; then
  mkdir -p "$TLS_DIR"
  if command -v openssl >/dev/null 2>&1; then
    bash "$ROOT/scripts/generate-runner-tls.sh" "$TLS_DIR"
  else
    docker run --rm --entrypoint /bin/sh -v "$ROOT/scripts:/work:ro" -v "$TLS_DIR:/out" \
      alpine/openssl:3.3.0 -c "mkdir -p /out && cp /work/generate-runner-tls.sh /tmp/gen.sh && sh /tmp/gen.sh /out" \
      || { echo "::error::无法生成 TLS 证书"; exit 2; }
  fi
fi

# ── 3. 隔离 Docker Engine（演练用 dind）────────────────────────────────
DIND_NAME="hfusionhub-rehearsal-dind"
if [[ "${USE_DIND:-1}" == "1" ]]; then
  if docker ps --format '{{.Names}}' | grep -qx "$DIND_NAME"; then
    echo "[dind] 演练引擎已在运行：$DIND_NAME"
  else
    echo "[dind] 启动隔离演练引擎（docker:dind）…"
    docker rm -f "$DIND_NAME" >/dev/null 2>&1
    if docker run -d --privileged --name "$DIND_NAME" \
        -p 127.0.0.1:2376:2376 \
        docker:dind --host=tcp://0.0.0.0:2376 2>/dev/null; then
      echo "[dind] 演练引擎已启动：$DIND_NAME"
    else
      echo "::warning::无法启动 dind（嵌套虚拟化可能被禁）。runner 将无法连引擎，预期 503。"
      USE_DIND=0
    fi
  fi
fi

# DOCKER_HOST 注入（生产由真实隔离引擎地址覆盖）
if [[ "${USE_DIND:-0}" == "1" ]]; then
  if grep -qE '^PLUGIN_RUNNER_DOCKER_HOST=' "$ENV_FILE"; then
    sed -i "s|^PLUGIN_RUNNER_DOCKER_HOST=.*|PLUGIN_RUNNER_DOCKER_HOST=tcp://host.docker.internal:2376|" "$ENV_FILE"
  else
    echo "PLUGIN_RUNNER_DOCKER_HOST=tcp://host.docker.internal:2376" >> "$ENV_FILE"
  fi
  if ! grep -qE '^PLUGIN_RUNNER_CA_CERT_FILE=' "$ENV_FILE"; then
    echo "PLUGIN_RUNNER_CA_CERT_FILE=$TLS_DIR/ca.pem"            >> "$ENV_FILE"
    echo "PLUGIN_RUNNER_CLIENT_CERT_FILE=$TLS_DIR/cert.pem"       >> "$ENV_FILE"
    echo "PLUGIN_RUNNER_CLIENT_KEY_FILE=$TLS_DIR/key.pem"         >> "$ENV_FILE"
  fi
fi

# TLS 证书文件路径必须以绝对路径写入 .env（compose 的 file: secret 相对
# project-directory 解析，相对路径会指向 deploy/deploy/... 而找不到）。
# 无论是否使用 dind 都需提供，runner 容器挂载这些 secret。
if ! grep -qE '^PLUGIN_RUNNER_CA_CERT_FILE=' "$ENV_FILE"; then
  echo "PLUGIN_RUNNER_CA_CERT_FILE=$TLS_DIR/ca.pem"              >> "$ENV_FILE"
  echo "PLUGIN_RUNNER_CLIENT_CERT_FILE=$TLS_DIR/cert.pem"         >> "$ENV_FILE"
  echo "PLUGIN_RUNNER_CLIENT_KEY_FILE=$TLS_DIR/key.pem"           >> "$ENV_FILE"
fi

# ── 4. 拉起全链路 ───────────────────────────────────────────────────────
echo "==> 拉起 prod compose（首次会构建镜像，耗时较长）…"
(cd "$ROOT" && docker compose -f "$COMPOSE" up -d --build)
rc=$?
if [[ $rc -ne 0 ]]; then
  echo "::error::compose up 失败 rc=$rc"
  (cd "$ROOT" && docker compose -f "$COMPOSE" ps)
  exit 1
fi

# ── 5. 健康校验 ─────────────────────────────────────────────────────────
SERVICES=(mysql8 redis7 milvus java-backend plugin-runner python-ai frontend)

health_of() { # $1=service -> stdout "healthy"/"starting"/""/nil
  docker compose -f "$COMPOSE" ps --format '{{.Service}}|{{.Health}}' 2>/dev/null \
    | awk -F'|' -v svc="$1" '$1==svc {print $2; found=1; exit} END{}'
}

wait_healthy() {
  local svc="$1" tries="${2:-60}"
  for ((i=0; i<tries; i++)); do
    local h; h=$(health_of "$svc")
    [[ "$h" == "healthy" ]] && return 0
    sleep 3
  done
  return 1
}

fails=()
for svc in "${SERVICES[@]}"; do
  echo -n "[health] waiting $svc …"
  if wait_healthy "$svc"; then
    echo " OK"
  else
    local_h=$(health_of "$svc")
    echo " FAIL(health=${local_h:-nil})"
    fails+=("$svc")
  fi
done

# ── 6. 报告 ─────────────────────────────────────────────────────────────
echo ""
echo "===== Staging 演练报告 ====="
for svc in "${SERVICES[@]}"; do
  h=$(health_of "$svc")
  echo "  $svc : ${h:-nil}"
done

echo ""
echo "  端点探活:"
probe() { curl -fsS -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo "DOWN"; }
echo "    java    /api/health -> $(probe http://127.0.0.1:8080/api/health)"
echo "    python  /ready      -> $(probe http://127.0.0.1:9000/ready)"
echo "    runner  /health     -> $(probe http://127.0.0.1:9100/health)"
echo "    frontend /          -> $(probe http://127.0.0.1:80/)"

if [[ ${#fails[@]} -eq 0 ]] && [[ "${USE_DIND:-0}" == "1" ]]; then
  echo "结论：全链路健康（runner 已连演练引擎）。"
  exit 0
elif [[ ${#fails[@]} -eq 0 ]] && [[ "${USE_DIND:-0}" != "1" ]]; then
  echo "结论：应用全链路 healthy，但 runner 未连隔离引擎（预期 503）。"
  echo "      如需全绿，请提供真实 PLUGIN_RUNNER_DOCKER_HOST 或启用嵌套虚拟化。"
  exit 3
else
  echo "结论：演练失败 —— 未 healthy: ${fails[*]}"
  (cd "$ROOT" && docker compose -f "$COMPOSE" logs --tail=50 "${fails[@]}" 2>/dev/null || true)
  exit 1
fi