<#
.SYNOPSIS
    HFusionHub 一键启动入口：依赖检查 → 生成环境配置 → 启动基础设施 → 等待健康 → 打印访问地址。

.DESCRIPTION
    默认模式：仅启动基础设施（MySQL / Redis / MinIO / Plugin Runner），
    然后提示在三个终端分别启动 Java / Python / 前端（适合开发、热重载）。
    加 -FullStack：全部服务容器化启动（Java / Python / 前端 镜像自动构建或拉取），
    一条命令即可体验完整平台。

.PARAMETER FullStack
    全部服务容器化启动（含镜像构建）。

.PARAMETER Reset
    重新生成全部随机口令（传给 init-env.ps1）。

.EXAMPLE
    .\scripts\setup.ps1                 # 基础设施 + 三终端开发指引
    .\scripts\setup.ps1 -FullStack      # 一键容器化启动全平台
#>
param([switch]$FullStack, [switch]$Reset)
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot

# docker compose ps --format json 输出为空或非法时返回空数组（PS 5.1 兼容）
function Get-ComposePs {
    $json = docker compose ps --format json 2>$null
    if (-not $json) { return @() }
    try { return @($json | ConvertFrom-Json) } catch { return @() }
}

function Test-Command($Name) {
    Get-Command $Name -ErrorAction SilentlyContinue -CommandType Application | Select-Object -First 1
}

# ── 1. 依赖检查 ─────────────────────────────────────────────
Write-Host "==> [1/4] 检查前置依赖"
if (-not (Test-Command docker)) { Write-Host "[FAIL] 未找到 docker，请先安装 Docker Desktop 并启动" -ForegroundColor Red; exit 1 }
try { docker info *> $null } catch { }
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Docker 守护进程未运行。请启动 Docker Desktop 后重试。" -ForegroundColor Red
    exit 1
}
if ($FullStack) {
    if (-not (Test-Command java) -and -not (Test-Command mvn)) { Write-Host "[warn] -FullStack 无需本机 Java/Maven（镜像内构建）" -ForegroundColor Yellow }
} else {
    foreach ($c in @('java', 'mvn', 'python', 'npm')) {
        if (-not (Test-Command $c)) { Write-Host "[warn] 未找到 $c（开发模式需要；若用 -FullStack 可忽略）" -ForegroundColor Yellow }
    }
}
Write-Host "  [ok] 依赖检查完成"

# ── 2. 生成环境配置 ─────────────────────────────────────────
Write-Host "==> [2/4] 生成环境配置"
if ($Reset) { & (Join-Path $PSScriptRoot 'init-env.ps1') -Reset } else { & (Join-Path $PSScriptRoot 'init-env.ps1') }
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] init-env 失败" -ForegroundColor Red; exit 1 }

# ── 3. 启动基础设施 ─────────────────────────────────────────
Write-Host "==> [3/4] 启动基础设施（MySQL / Redis / MinIO / Plugin Runner）"
Push-Location (Join-Path $repoRoot 'docker')
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose up 失败" }

    # 等待基础设施健康
    Write-Host "  ... 等待 mysql8 / redis7 健康（最多 120 秒）"
    $deadline = (Get-Date).AddSeconds(120)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        $ps = Get-ComposePs
        $svcs = @($ps | Where-Object { $_.Service -in @('mysql8', 'redis7') })
        if ($svcs.Count -eq 2 -and ($svcs | Where-Object { $_.Health -ne 'healthy' }).Count -eq 0) { $healthy = $true; break }
        Start-Sleep -Seconds 5
    }
    if (-not $healthy) {
        Write-Host "[FAIL] 基础设施未在 120 秒内就绪，请运行 docker compose ps 检查" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [ok] 基础设施已就绪"
}
finally { Pop-Location }

# ── 4. 应用服务 ─────────────────────────────────────────────
if ($FullStack) {
    Write-Host "==> [4/4] 启动全平台（构建/拉取 Java + Python + Frontend 镜像）"
    Push-Location (Join-Path $repoRoot 'docker')
    try {
        docker compose --profile fullstack up -d --build
        if ($LASTEXITCODE -ne 0) { throw "fullstack 启动失败" }
        Write-Host "  ... 等待 java-backend / python-ai / frontend 健康（最多 240 秒）"
        $deadline = (Get-Date).AddSeconds(240)
        $healthy = $false
        while ((Get-Date) -lt $deadline) {
            $ps = Get-ComposePs
            $svcs = @($ps | Where-Object { $_.Service -in @('java-backend', 'python-ai', 'frontend') })
            if ($svcs.Count -eq 3 -and ($svcs | Where-Object { $_.Health -ne 'healthy' }).Count -eq 0) { $healthy = $true; break }
            Start-Sleep -Seconds 10
        }
        if (-not $healthy) {
            Write-Host "[warn] 应用服务未完全健康，请运行 docker compose -f docker/docker-compose.yml --profile fullstack ps 检查" -ForegroundColor Yellow
        } else {
            Write-Host "  [ok] 全平台已就绪"
        }
    }
    finally { Pop-Location }

    Write-Host ""
    Write-Host "=========================================="
    Write-Host "  HFusionHub 已启动："
    Write-Host "    前端:    http://localhost:3000"
    Write-Host "    Java API: http://localhost:8080/api"
    Write-Host "    Python AI: http://localhost:9000/health"
    Write-Host "    API 文档: http://localhost:8080/api/doc.html"
    Write-Host "=========================================="
} else {
    Write-Host ""
    Write-Host "=========================================="
    Write-Host "  基础设施已启动。请打开三个终端分别运行："
    Write-Host "  终端1 (Java):   .\start-java.sh 或 cd java-backend; mvn spring-boot:run"
    Write-Host "                  （需先设置环境变量，见 docs/ENVIRONMENT.md）"
    Write-Host "  终端2 (Python): cd python-ai; .venv\Scripts\Activate.ps1; python -m app.main"
    Write-Host "  终端3 (前端):   cd hfusionhub-frontend; npm ci; npm run dev"
    Write-Host ""
    Write-Host "  或一条命令全部容器化:  .\scripts\setup.ps1 -FullStack"
    Write-Host "=========================================="
}
