#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="deploy/docker-compose.prod.yml"
PROJECT_NAME="deploy"
ENV_FILE="$ROOT/deploy/.env"
TLS_DIR="$ROOT/deploy/runner-tls"
ACTION="up"
PRUNE_VOLUMES=0
USE_DIND=1
DIND_PROXY="${DIND_PROXY:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --down) ACTION="down" ;;
    --no-dind) USE_DIND=0 ;;
    --prune-volumes) PRUNE_VOLUMES=1 ;;
    --dind-proxy)
      DIND_PROXY="${2:-}"
      [[ -n "$DIND_PROXY" ]] || { echo "::error::--dind-proxy needs a URL" >&2; exit 2; }
      shift
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

need() { command -v "$1" >/dev/null 2>&1 || { echo "::error::missing: $1" >&2; exit 2; }; }
need docker
need bash
docker compose version >/dev/null 2>&1 || { echo "::error::docker compose is unavailable" >&2; exit 2; }

if [[ "$ACTION" == "down" ]]; then
  if [[ "$PRUNE_VOLUMES" == "1" ]]; then
    (cd "$ROOT" && docker compose -f "$COMPOSE" down -v --remove-orphans)
  else
    (cd "$ROOT" && docker compose -f "$COMPOSE" down --remove-orphans)
  fi
  DIND_NAME="hfusionhub-rehearsal-dind"
  if docker ps -a --format '{{.Names}}' | grep -qx "$DIND_NAME"; then
    docker rm -f "$DIND_NAME" >/dev/null 2>&1 || true
  fi
  echo "staging stopped (volumes are preserved unless --prune-volumes is used)."
  exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/deploy/.env.example" "$ENV_FILE"
fi
random_hex() { docker run --rm alpine:3.20 sh -c "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'" 2>/dev/null; }
ensure_key() {
  local var="$1"
  if ! grep -qE "^${var}=[^ ]+" "$ENV_FILE"; then
    echo "${var}=$(random_hex)" >> "$ENV_FILE"
  fi
}
for key in MYSQL_ROOT_PASSWORD MYSQL_PASSWORD PYTHON_AI_INTERNAL_TOKEN \
           CALLBACK_SECRET ADMIN_PASSWORD PLUGIN_RUNNER_TOKEN DEEPSEEK_API_KEY; do
  ensure_key "$key"
done

if [[ ! -f "$TLS_DIR/ca.pem" || ! -f "$TLS_DIR/cert.pem" || ! -f "$TLS_DIR/key.pem" ]]; then
  mkdir -p "$TLS_DIR"
  if command -v openssl >/dev/null 2>&1; then
    bash "$ROOT/scripts/generate-runner-tls.sh" "$TLS_DIR"
  else
    docker run --rm --entrypoint /bin/sh -v "$ROOT/scripts:/work:ro" -v "$TLS_DIR:/out" \
      alpine/openssl:3.3.0 -c "cp /work/generate-runner-tls.sh /tmp/gen.sh && sh /tmp/gen.sh /out" \
      || { echo "::error::unable to generate TLS certificates" >&2; exit 2; }
  fi
fi
if [[ ! -f "$TLS_DIR/dind-certs/server/ca.pem" || ! -f "$TLS_DIR/dind-certs/server/cert.pem" || \
      ! -f "$TLS_DIR/dind-certs/server/key.pem" || ! -f "$TLS_DIR/dind-certs/client/ca.pem" || \
      ! -f "$TLS_DIR/dind-certs/client/cert.pem" || ! -f "$TLS_DIR/dind-certs/client/key.pem" ]]; then
  bash "$ROOT/scripts/generate-runner-tls.sh" "$TLS_DIR" --dind-layout \
    || { echo "::error::unable to prepare docker:dind TLS layout" >&2; exit 2; }
fi

DIND_NAME="hfusionhub-rehearsal-dind"
DIND_CERTS_DIR="$TLS_DIR/dind-certs"
normalize_proxy() {
  local proxy="$1"
  printf '%s' "$proxy" | sed -E 's#://(127\.0\.0\.1|localhost)(:|/)#://host.docker.internal\2#'
}
dind_docker() {
  DOCKER_HOST=tcp://127.0.0.1:2376 DOCKER_TLS_VERIFY=1 \
    DOCKER_CERT_PATH="$DIND_CERTS_DIR/client" docker "$@"
}
wait_for_dind() {
  for _ in $(seq 1 30); do
    if dind_docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  return 1
}

if [[ "$USE_DIND" == "1" ]]; then
  if ! docker ps --format '{{.Names}}' | grep -qx "$DIND_NAME"; then
    docker rm -f "$DIND_NAME" >/dev/null 2>&1 || true
    dind_args=(run -d --privileged --name "$DIND_NAME"
      -p 127.0.0.1:2376:2376 -e DOCKER_TLS_CERTDIR=/certs
      -v "$DIND_CERTS_DIR:/certs:ro")
    if [[ -n "$DIND_PROXY" ]]; then
      dind_proxy_host="$(normalize_proxy "$DIND_PROXY")"
      dind_args+=(-e "HTTP_PROXY=$dind_proxy_host" -e "HTTPS_PROXY=$dind_proxy_host"
        -e "NO_PROXY=localhost,127.0.0.1,host.docker.internal")
    fi
    dind_args+=(docker:dind)
    if ! docker "${dind_args[@]}" >/dev/null 2>&1 || ! wait_for_dind; then
      docker rm -f "$DIND_NAME" >/dev/null 2>&1 || true
      echo "::warning::dind TLS handshake failed; runner will remain unavailable." >&2
      USE_DIND=0
    fi
  fi
  if [[ "$USE_DIND" == "1" ]] && ! wait_for_dind; then
    docker rm -f "$DIND_NAME" >/dev/null 2>&1 || true
    USE_DIND=0
  fi
fi

if [[ "$USE_DIND" != "1" ]]; then
  # Do not let an earlier rehearsal make a --no-dind run appear healthy.
  docker rm -f "$DIND_NAME" >/dev/null 2>&1 || true
fi

upsert_env() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}
upsert_env PLUGIN_RUNNER_CA_CERT_FILE "$TLS_DIR/ca.pem"
upsert_env PLUGIN_RUNNER_CLIENT_CERT_FILE "$TLS_DIR/cert.pem"
upsert_env PLUGIN_RUNNER_CLIENT_KEY_FILE "$TLS_DIR/key.pem"
runner_docker_host="tcp://127.0.0.1:2377"
[[ "$USE_DIND" == "1" ]] && runner_docker_host="tcp://host.docker.internal:2376"
if ! (cd "$ROOT" && PLUGIN_RUNNER_DOCKER_HOST="$runner_docker_host" docker compose -f "$COMPOSE" up -d --build); then
  (cd "$ROOT" && docker compose -f "$COMPOSE" ps)
  exit 1
fi

SERVICES=(mysql8 redis7 milvus java-backend plugin-runner python-ai frontend)
health_of() {
  docker compose -f "$COMPOSE" ps --format '{{.Service}}|{{.Health}}' 2>/dev/null \
    | awk -F'|' -v svc="$1" '$1==svc {print $2; exit}'
}
wait_healthy() {
  local svc="$1"
  for _ in $(seq 1 60); do
    [[ "$(health_of "$svc")" == "healthy" ]] && return 0
    sleep 3
  done
  return 1
}
fails=()
for svc in "${SERVICES[@]}"; do
  if wait_healthy "$svc"; then echo "[health] $svc OK"; else fails+=("$svc"); fi
done

echo "===== Staging rehearsal ====="
for svc in "${SERVICES[@]}"; do echo "  $svc : $(health_of "$svc")"; done
probe() { curl -fsS -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo DOWN; }
echo "  java     /api/health -> $(probe http://127.0.0.1:8080/api/health)"
echo "  python   /ready      -> $(probe http://127.0.0.1:9000/ready)"
echo "  runner   /health     -> $(docker exec hfusionhub-plugin-runner sh -c 'curl -s http://127.0.0.1:9100/health' 2>/dev/null || echo DOWN)"
echo "  frontend /           -> $(probe http://127.0.0.1:80/)"

runner_health="$(docker exec hfusionhub-plugin-runner sh -c 'curl -s http://127.0.0.1:9100/health' 2>/dev/null || true)"
if [[ "$USE_DIND" == "1" && "$runner_health" != *'"docker_connected":true'* ]]; then
  fails+=(plugin-runner-engine)
elif [[ "$USE_DIND" != "1" && "$runner_health" == *'"docker_connected":true'* ]]; then
  fails+=(plugin-runner-fail-closed)
fi

if [[ ${#fails[@]} -ne 0 ]]; then
  echo "staging failed; unhealthy services: ${fails[*]}" >&2
  (cd "$ROOT" && docker compose -f "$COMPOSE" logs --tail=50 "${fails[@]}" 2>/dev/null || true)
  exit 1
fi
if [[ "$USE_DIND" == "1" ]]; then
  echo "staging healthy; runner is connected to the isolated Docker Engine."
  exit 0
fi
echo "staging healthy; runner has no isolated engine (expected 503)."
exit 3
