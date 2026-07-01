#!/usr/bin/env bash
# HFusionHub 一键启动入口：依赖检查 → 生成环境配置 → 启动基础设施 → 等待健康 → 打印访问地址。
#
# 用法:
#   bash scripts/setup.sh              # 基础设施 + 三终端开发指引
#   bash scripts/setup.sh --fullstack  # 全部服务容器化启动（一条命令体验完整平台）
#   bash scripts/setup.sh --reset      # 重新生成全部随机口令
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FULLSTACK=false
RESET=false
for arg in "$@"; do
  case "$arg" in
    --fullstack) FULLSTACK=true ;;
    --reset) RESET=true ;;
    *) echo "未知参数: $arg"; exit 1 ;;
  esac
done

say()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
ok()   { printf '  \033[32m[ok]\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m[FAIL]\033[0m %s\n' "$1"; exit 1; }

# ── 1. 依赖检查 ─────────────────────────────────────────────
say "[1/4] 检查前置依赖"
command -v docker >/dev/null 2>&1 || fail "未找到 docker，请先安装 Docker 并启动守护进程"
docker info >/dev/null 2>&1 || fail "Docker 守护进程未运行，请先启动 Docker"
if [[ "$FULLSTACK" != true ]]; then
  for c in java mvn python3 npm; do
    command -v "$c" >/dev/null 2>&1 || echo "  [warn] 未找到 $c（开发模式需要；若用 --fullstack 可忽略）"
  done
fi
ok "依赖检查完成"

# ── 2. 生成环境配置 ─────────────────────────────────────────
say "[2/4] 生成环境配置"
if [[ "$RESET" == true ]]; then
  bash "$REPO_ROOT/scripts/init-env.sh" --reset
else
  bash "$REPO_ROOT/scripts/init-env.sh"
fi

# ── 3. 启动基础设施 ─────────────────────────────────────────
say "[3/4] 启动基础设施（MySQL / Redis / MinIO / Plugin Runner）"
cd "$REPO_ROOT/docker"
docker compose up -d
echo "  ... 等待 mysql8 / redis7 健康（最多 120 秒）"
deadline=$(( $(date +%s) + 120 ))
healthy=false
while (( $(date +%s) < deadline )); do
  statuses=$(docker compose ps --format json 2>/dev/null | python3 -c "
import json,sys
try:
    data=json.load(sys.stdin)
except Exception:
    sys.exit(1)
rows=data if isinstance(data,list) else [data]
want={'mysql8','redis7'}
if {r.get('Service') for r in rows} >= want and all(r.get('Health')=='healthy' for r in rows if r.get('Service') in want):
    print('healthy')
" 2>/dev/null || echo "")
  if [[ "$statuses" == "healthy" ]]; then healthy=true; break; fi
  sleep 5
done
[[ "$healthy" == true ]] || fail "基础设施未在 120 秒内就绪，请运行 docker compose ps 检查"
ok "基础设施已就绪"

# ── 4. 应用服务 ─────────────────────────────────────────────
if [[ "$FULLSTACK" == true ]]; then
  say "[4/4] 启动全平台（构建/拉取 Java + Python + Frontend 镜像）"
  docker compose --profile fullstack up -d --build
  echo "  ... 等待 java-backend / python-ai / frontend 健康（最多 240 秒）"
  deadline=$(( $(date +%s) + 240 ))
  healthy=false
  while (( $(date +%s) < deadline )); do
    statuses=$(docker compose ps --format json 2>/dev/null | python3 -c "
import json,sys
try:
    data=json.load(sys.stdin)
except Exception:
    sys.exit(1)
rows=data if isinstance(data,list) else [data]
want={'java-backend','python-ai','frontend'}
if {r.get('Service') for r in rows} >= want and all(r.get('Health')=='healthy' for r in rows if r.get('Service') in want):
    print('healthy')
" 2>/dev/null || echo "")
    if [[ "$statuses" == "healthy" ]]; then healthy=true; break; fi
    sleep 10
  done
  [[ "$healthy" == true ]] || echo "  [warn] 应用服务未完全健康，请运行 docker compose --profile fullstack ps 检查"
  ok "全平台启动流程结束"
  cat <<EOF

==========================================
  HFusionHub 已启动：
    前端:      http://localhost:3000
    Java API:  http://localhost:8080/api
    Python AI: http://localhost:9000/health
    API 文档:  http://localhost:8080/api/doc.html
==========================================
EOF
else
  cat <<EOF

==========================================
  基础设施已启动。请打开三个终端分别运行：
  终端1 (Java):   ./start-java.sh 或 cd java-backend && mvn spring-boot:run
                  （必需变量：PYTHON_AI_INTERNAL_TOKEN / CALLBACK_SECRET /
                   ADMIN_PASSWORD / MINIO_ACCESS_KEY / MINIO_SECRET_KEY，
                   已由 init-env 写入 docker/.env，可 source docker/.env 后再启动；
                   完整清单见 docs/ENVIRONMENT.md「Java Backend」节）
  终端2 (Python): cd python-ai && source .venv/bin/activate && python -m app.main
  终端3 (前端):   cd hfusionhub-frontend && npm ci && npm run dev

  或一条命令全部容器化:  bash scripts/setup.sh --fullstack
==========================================
EOF
fi
