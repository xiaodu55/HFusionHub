#!/usr/bin/env pwsh
# demo-trace.ps1 — 分布式追踪一键演示（第二十二批）
#
# 前提:
#   1. 监控栈已启动: docker compose -f deploy\docker-compose.monitoring.yml up -d
#   2. Java 以 TRACING_ENABLED=true + OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces 运行
#      （Python 侧可选: OTEL_ENABLED=true 同样上报）
#
# 效果: 发送 3 次带 W3C traceparent 的真实请求 → 在 Tempo 中检索本次调用链 →
#       打印可在 Grafana → Explore → Tempo 粘贴的 trace id。
#
# 用法: .\scripts\demo-trace.ps1

param(
    [string]$JavaUrl = 'http://localhost:8080',
    [string]$TempoUrl = 'http://localhost:3200',
    [string]$GrafanaUrl = 'http://localhost:3001'
)

$ErrorActionPreference = 'Stop'
$envFile = Join-Path (Split-Path -Parent $PSScriptRoot) 'docker\.env'

# 0. Tempo 就绪检查
try {
    $ready = Invoke-RestMethod -Uri "$TempoUrl/ready" -TimeoutSec 5
    if ("$ready" -notmatch 'ready') { throw "Tempo 返回: $ready" }
} catch {
    Write-Host "[ERROR] Tempo 未就绪（$TempoUrl）。先启动监控栈：" -ForegroundColor Red
    Write-Host '  docker compose -f deploy\docker-compose.monitoring.yml up -d' -ForegroundColor Yellow
    exit 1
}
Write-Host '✓ Tempo 就绪' -ForegroundColor Green

# 1. 登录拿 token（凭据权威来源 docker\.env）
$envLines = Get-Content $envFile
$adminPw = ($envLines | Where-Object { $_ -match '^\s*ADMIN_PASSWORD=' } | Select-Object -First 1) -replace '^\s*ADMIN_PASSWORD=', ''
if (-not $adminPw) { Write-Host '[ERROR] docker\.env 缺少 ADMIN_PASSWORD' -ForegroundColor Red; exit 1 }

$login = Invoke-RestMethod -Uri "$JavaUrl/api/user/login" -Method Post -Body (
    @{ username = 'admin'; password = $adminPw } | ConvertTo-Json) -ContentType 'application/json' -TimeoutSec 20
$headers = @{ satoken = $login.data }

# 2. 生成 W3C traceparent（随机 trace id + span id）
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
function RandomHex([int]$bytes) {
    $buf = [byte[]]::new($bytes); $rng.GetBytes($buf)
    return (($buf | ForEach-Object { $_.ToString('x2') }) -join '')
}
$traceId = RandomHex 16
$spanId = RandomHex 8
$traceparent = "00-$traceId-$spanId-01"
Write-Host "✓ 本次演示 traceparent: $traceparent" -ForegroundColor Cyan

# 3. 发 3 次真实请求（401/200 都会生成服务端 span）
foreach ($path in @('/api/auth/me', '/api/quota/summary', '/api/system/ai-health')) {
    try {
        Invoke-RestMethod -Uri "$JavaUrl$path" -Headers $headers -TimeoutSec 15 | Out-Null
    } catch {
        # 非 2xx 也无妨——服务端 span 照样生成
    }
    Write-Host "  请求 $path ✓"
}
Write-Host '等待 span 批量导出（约 5 秒）...'; Start-Sleep -Seconds 5

# 4. 在 Tempo 中检索本 trace
try {
    $trace = Invoke-RestMethod -Uri "$TempoUrl/api/traces/$traceId" -Headers @{ Accept = 'application/json' } -TimeoutSec 10
    Write-Host "✓ Tempo 中已检索到调用链 traceId=$traceId" -ForegroundColor Green
    $trace | ConvertTo-Json -Depth 4 | Out-Null
} catch {
    Write-Host "[!] 未能按 id 检索到 trace $traceId —— 确认 Java 以 TRACING_ENABLED=true 启动，稍后重试" -ForegroundColor Yellow
    exit 1
}

Write-Host ''
Write-Host '══ 演示查看方式 ══' -ForegroundColor Cyan
Write-Host "1. 打开 Grafana: $GrafanaUrl/explore （账号 admin，密码见 deploy\.env 的 GRAFANA_ADMIN_PASSWORD）"
Write-Host '2. 数据源选 Tempo → 查询类型 TraceQL，输入: {service.name="hfusionhub-backend"}'
Write-Host "3. 或直接粘贴 trace id: $traceId"
Write-Host '4. Python 侧链路（可选）: 以 OTEL_ENABLED=true 重启 python-ai 后重复本脚本'
