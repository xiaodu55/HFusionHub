#!/usr/bin/env bash
# ═════════════════════════════════════════════════════════════════════════
# plugin-provision.sh — 平台内建插件（P2-3：bid_docx / bid_quote）构建与上架
#
# 对每个插件：
#   1. 构建 wheel（含 <wheel>.sha256 sidecar，供 Python 启动加载器供应链校验）
#   2. 构建容器镜像（host daemon，Dockerfile.plugin-<name>）
#   3. dev：docker save/load 载入本地 dind（runner 经 host.docker.internal:2376 使用）
#      prod（HUB_DOCKER_REGISTRY）：推送 registry
#   4. 计算镜像 digest：
#        - 本地构建：config digest（{{.Id}}）——镜像从未推送，runner 按此常量时间比较
#        - registry：RepoDigest
#   5. 回填 plugin.image_digest（经 mysql8 容器 UPDATE V73 种子行，tenant_id IS NULL），
#      供 Java /internal/plugin/{id}/versions + Python 容器执行链使用
#
# 用法：
#   ./scripts/plugin-provision.sh                                  # dev（默认）
#   HUB_DOCKER_REGISTRY=reg.example.com/hf ./scripts/plugin-provision.sh  # prod 推送
#
# 环境变量：
#   HUB_MYSQL_CONTAINER   mysql 容器名（默认 mysql8）
#   HUB_DIND_HOST         本地 dind TLS 地址（默认 tcp://127.0.0.1:2376）
#   HUB_DIND_CERT_DIR     dind 客户端证书目录（默认 deploy/runner-tls/dind-certs/client）
#
# 前置：Docker daemon 可用；dev 场景 dind + plugin-runner 已启动（staging-rehearsal.sh）；
#       docker/.env 含 MYSQL_PASSWORD（读取自 .env，可被 HUB_MYSQL_PASSWORD 覆盖）。
# ═════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── 插件清单 ───────────────────────────────────────────────────────────
# 插件 name（wheel/manifest 用下划线）→ 镜像名（容器 tag 用连字符，如 hfusionhub-plugin-bid-docx）
PLUGINS=(bid_docx bid_quote)
VERSION="1.0.0"
declare -A PLUGIN_IMAGE=(
  [bid_docx]="hfusionhub-plugin-bid-docx"
  [bid_quote]="hfusionhub-plugin-bid-quote"
)

# ── 环境覆盖 ───────────────────────────────────────────────────────────
HUB_MYSQL_CONTAINER="${HUB_MYSQL_CONTAINER:-mysql8}"
HUB_DIND_HOST="${HUB_DIND_HOST:-tcp://127.0.0.1:2376}"
HUB_DIND_CERT_DIR="${HUB_DIND_CERT_DIR:-$ROOT/deploy/runner-tls/dind-certs/client}"
HUB_DOCKER_REGISTRY="${HUB_DOCKER_REGISTRY:-}"

# MySQL 凭据：优先环境变量，否则读 docker/.env
HUB_MYSQL_PASSWORD="${HUB_MYSQL_PASSWORD:-}"
if [[ -z "$HUB_MYSQL_PASSWORD" && -f "$ROOT/docker/.env" ]]; then
  HUB_MYSQL_PASSWORD="$(sed -n 's/^MYSQL_PASSWORD=//p' "$ROOT/docker/.env" | head -1 | tr -d '\r')"
fi

# ── 工具函数 ───────────────────────────────────────────────────────────
log()  { printf '\n\033[1;36m[provision] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[provision] ERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# 通过本地 dind（TLS 客户端证书）驱动 docker
dind_docker() {
  DOCKER_HOST="$HUB_DIND_HOST" DOCKER_TLS_VERIFY=1 \
    DOCKER_CERT_PATH="$HUB_DIND_CERT_DIR" docker "$@"
}

compute_digest() {
  local image="$1"
  if [[ -n "$HUB_DOCKER_REGISTRY" ]]; then
    docker inspect --format '{{index .RepoDigests 0}}' "$HUB_DOCKER_REGISTRY/$image" 2>/dev/null \
      || die "registry 镜像 $HUB_DOCKER_REGISTRY/$image 的 RepoDigest 不存在（是否已推送？）"
  else
    # 本地构建镜像（从未推送）：config digest {{.Id}}，runner 按此常量时间比较
    docker inspect --format '{{.Id}}' "$image" || die "本地镜像 $image 的 config digest 获取失败"
  fi
}

backfill_digest() {
  local name="$1" digest="$2"
  [[ -n "$HUB_MYSQL_PASSWORD" ]] || die "缺少 MYSQL_PASSWORD（docker/.env 或 HUB_MYSQL_PASSWORD）"
  log "回填 plugin.image_digest: $name=$digest"
  docker exec "$HUB_MYSQL_CONTAINER" mysql -uhfusionhub -p"$HUB_MYSQL_PASSWORD" hfusionhub \
    -e "UPDATE plugin SET image_digest='$digest' WHERE name='$name' AND version='$VERSION' AND tenant_id IS NULL;"
}

# ── 1. 构建 wheel ──────────────────────────────────────────────────────
log "构建 wheel（含 .sha256 sidecar）"
PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$ROOT/python-ai/.venv/Scripts/python.exe" ]]; then
    PYTHON="$ROOT/python-ai/.venv/Scripts/python.exe"
  else
    PYTHON="python"
  fi
fi
"$PYTHON" python-ai/plugins/build_wheel.py "${PLUGINS[@]}" >/dev/null

# ── 1b. 平台签名（.sig + 信任策略注册）────────────────────────────────
# python-ai 启动加载器对 wheel 强制 Ed25519 签名校验（app/core/plugin/loader.py
# verify_sig=True）：平台私钥默认 deploy/plugin-signing/（gitignored，首次生成），
# 公钥注册进信任策略目录（python-ai 运行时须指向同一目录）。
HUB_PLUGIN_TRUST_DIR="${HFUSIONHUB_PLUGIN_TRUST_DIR:-$ROOT/python-ai/plugins/trust}"
# Windows Python 不识别 git-bash 的 /d/... 形式，统一转成 D:/... 混合形式
win_trust_dir="$(cygpath -m "$HUB_PLUGIN_TRUST_DIR" 2>/dev/null || echo "$HUB_PLUGIN_TRUST_DIR")"
export HFUSIONHUB_PLUGIN_TRUST_DIR="$win_trust_dir"
log "平台签名 + 信任策略注册（trust dir=$win_trust_dir）"
"$PYTHON" python-ai/plugins/sign_wheels.py "${PLUGINS[@]}"

# ── 2-4. 构建镜像 + digest + 上架 ──────────────────────────────────────
for name in "${PLUGINS[@]}"; do
  image_name="${PLUGIN_IMAGE[$name]}"
  image="$image_name:$VERSION"
  dockerfile="docker/Dockerfile.plugin-${image_name#hfusionhub-plugin-}"
  log "构建镜像 $image（$dockerfile）"
  docker build -q -t "$image" -f "$dockerfile" . >/dev/null \
    || die "镜像 $image 构建失败"

  if [[ -n "$HUB_DOCKER_REGISTRY" ]]; then
    # prod：推送 registry，用 RepoDigest 作供应链校验锚点
    docker tag "$image" "$HUB_DOCKER_REGISTRY/$image"
    docker push "$HUB_DOCKER_REGISTRY/$image" >/dev/null
  else
    # dev：save → 载入本地 dind（runner 的执行目标）
    log "载入镜像进 dind: $image"
    tar_dir="$ROOT/python-ai/plugins/dist"
    mkdir -p "$tar_dir"
    tar_path="$tar_dir/.${name}-${VERSION}.tar"
    docker save -o "$tar_path" "$image"
    win_tar="$(cygpath -w "$tar_path" 2>/dev/null || echo "$tar_path")"
    dind_docker load -i "$win_tar" >/dev/null
    rm -f "$tar_path"
  fi

  digest="$(compute_digest "$image")"
  backfill_digest "$name" "$digest"
done

log "完成。平台内建插件已上架：${PLUGINS[*]}"
echo "  - 镜像已就绪（dev=dind / prod=$HUB_DOCKER_REGISTRY）"
echo "  - plugin.image_digest 已回填（V73 种子行，tenant_id IS NULL）"
echo "  - Python 启动时从 PLUGIN_BUILTIN_WHEELS_DIR 加载 wheel（供应链 sidecar 校验）"
