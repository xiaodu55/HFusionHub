#!/bin/sh
# -----------------------------------------------------------------------------
# HFusionHub — Plugin Runner Docker Engine TLS 证书生成
#
# 用途：为"隔离 Docker Engine"生成 TLS 证书三件套
#   deploy/runner-tls/ca.pem     （自建 CA 证书）
#   deploy/runner-tls/cert.pem   （客户端证书）
#   deploy/runner-tls/key.pem    （客户端私钥）
#
# 这些文件被 deploy/docker-compose.prod.yml 作为 Compose secrets 挂载到
# plugin-runner 容器的 /certs/client/{ca,cert,key}.pem，供 runner 通过
# DOCKER_HOST + DOCKER_TLS_VERIFY=1 访问远程 Docker Engine（绝不挂载
# /var/run/docker.sock）。Helm 场景则把三份内容放入同名 K8s Secret 后
# 用 pluginRunner.tlsSecretName 引用。
#
# 用法：
#   sh scripts/generate-runner-tls.sh [输出目录]
#   # 默认输出到 deploy/runner-tls/
#
# 也可在 CI 中预先生成（不提交任何私钥到仓库）。
#
# 兼容性：POSIX sh 书写（只用 `command -v openssl`，不用 bash 数组），
# 可直接在 alpine/openssl 容器内执行，也兼容 bash/dash/ash。
# -----------------------------------------------------------------------------
set -eu

OUT_DIR="${1:-deploy/runner-tls}"
DAYS=825          # ~27 个月，与 Let's Encrypt 等轮换节奏匹配
CA_DAYS=3650

# 证书主题可覆盖：CN 会被 Docker Engine 校验为受信任客户端。
CN="${TLS_CLIENT_CN:-hfusionhub-plugin-runner}"

mkdir -p "$OUT_DIR"

if command -v openssl >/dev/null 2>&1; then
  OPENSSL="openssl"
else
  echo "::error::openssl 未安装。本机可用 docker 容器代替：" \
    "docker run --rm -v \$(pwd):/work -w /work alpine/openssl ..." >&2
  exit 1
fi

# ── 1. 自建 CA ───────────────────────────────────────────────────────────
$OPENSSL genrsa -out "$OUT_DIR/ca-key.pem" 4096
$OPENSSL req -x509 -new -nodes -sha256 -days "$CA_DAYS" \
  -key "$OUT_DIR/ca-key.pem" \
  -out "$OUT_DIR/ca.pem" \
  -subj "/CN=hfusionhub-ca"

# ── 2. 客户端证书（runner → Docker Engine 的 TLS 客户端身份）──────────────
$OPENSSL genrsa -out "$OUT_DIR/key.pem" 4096
$OPENSSL req -new -key "$OUT_DIR/key.pem" \
  -out "$OUT_DIR/client.csr" \
  -subj "/CN=${CN}"
cat > "$OUT_DIR/extfile.cnf" <<EOF
extendedKeyUsage = clientAuth
EOF
$OPENSSL x509 -req -sha256 -days "$DAYS" \
  -in "$OUT_DIR/client.csr" \
  -CA "$OUT_DIR/ca.pem" \
  -CAkey "$OUT_DIR/ca-key.pem" \
  -CAcreateserial \
  -out "$OUT_DIR/cert.pem" \
  -extfile "$OUT_DIR/extfile.cnf"

# ── 3. 清理中间产物（CA 私钥默认保留，便于复签/轮换；介意可删除）──────────
rm -f "$OUT_DIR/client.csr" "$OUT_DIR/extfile.cnf"

# ── 4. 权限与校验 ────────────────────────────────────────────────────────
chmod 600 "$OUT_DIR/key.pem" "$OUT_DIR/ca-key.pem"
chmod 644 "$OUT_DIR/ca.pem" "$OUT_DIR/cert.pem"

echo "Runner TLS 证书已生成到 $OUT_DIR :"
ls -l "$OUT_DIR"
$OPENSSL x509 -in "$OUT_DIR/cert.pem" -noout -subject -dates
