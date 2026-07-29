#!/usr/bin/env pwsh
# run-all-benchmarks.ps1 — 运行完整性能基线测试套件
# 用法：.\scripts\run-all-benchmarks.ps1 > baseline-v1.0.0.txt

param(
    [string]$BaseUrl = 'http://localhost:8080',
    [string]$PythonUrl = 'http://localhost:9000',
    [string]$FrontendUrl = 'http://localhost:3000'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $RepoRoot 'docker\.env'

Write-Host "==== HFusionHub 性能基线测试 ====" -ForegroundColor Cyan
Write-Host "时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Java: $BaseUrl"
Write-Host "Python: $PythonUrl"
Write-Host "Frontend: $FrontendUrl"
Write-Host ""

# ── 辅助函数 ─────────────────────────────────────────────────────────
function Get-EnvVal($key) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$key=" } | Select-Object -First 1
    if ($line) { return ($line -split '=', 2)[1].Trim() }
    return ''
}

function Measure-Percentile($values, $p) {
    $sorted = $values | Sort-Object
    $idx = [math]::Floor($sorted.Count * $p)
    return $sorted[$idx]
}

# ── 0. 登录 ──────────────────────────────────────────────────────────
$adminPw = Get-EnvVal 'ADMIN_PASSWORD'
if (-not $adminPw) {
    Write-Host "[ERROR] docker\.env 缺少 ADMIN_PASSWORD" -ForegroundColor Red
    exit 1
}

Write-Host "登录中..." -ForegroundColor Yellow
$login = Invoke-RestMethod -Uri "$BaseUrl/api/user/login" -Method Post -Body (@{ username = 'admin'; password = $adminPw } | ConvertTo-Json) -ContentType 'application/json' -TimeoutSec 20
$headers = @{ satoken = $login.data }

# ── 1. Java API 性能 ──────────────────────────────────────────────────
Write-Host "`n==== 1. Java API 响应时间 ====" -ForegroundColor Cyan

$endpoints = @(
    @{n='用户信息';p='/user/info'},
    @{n='知识库列表';p='/knowledge-base/my?page=1&pageSize=10'},
    @{n='对话列表';p='/conversation/my?page=1&pageSize=10'},
    @{n='用量汇总';p='/cost/summary?days=30'},
    @{n='配额摘要';p='/quota/summary'}
)

foreach ($ep in $endpoints) {
    $durations = @()
    for ($i = 1; $i -le 50; $i++) {
        $start = Get-Date
        try {
            Invoke-RestMethod -Uri "$BaseUrl/api$($ep.p)" -Headers $headers -TimeoutSec 10 | Out-Null
            $durations += ((Get-Date) - $start).TotalMilliseconds
        } catch {
            Write-Host "  [FAIL] $($ep.n)" -ForegroundColor Red
        }
    }
    if ($durations.Count -gt 0) {
        $avg = ($durations | Measure-Object -Average).Average
        $p50 = Measure-Percentile $durations 0.5
        $p95 = Measure-Percentile $durations 0.95
        Write-Host "$($ep.n): Avg=$([math]::Round($avg))ms, P50=$([math]::Round($p50))ms, P95=$([math]::Round($p95))ms" -ForegroundColor Green
    }
}

# ── 2. RAG 检索性能 ───────────────────────────────────────────────────
Write-Host "`n==== 2. RAG 检索性能 ====" -ForegroundColor Cyan

$pyToken = Get-EnvVal 'PYTHON_AI_INTERNAL_TOKEN'
$pyHeaders = @{ 'X-Internal-Token' = $pyToken; 'X-Tenant-Id' = '1'; 'Content-Type' = 'application/json; charset=utf-8' }

$queries = @(
    'Java 虚拟线程如何工作',
    '如何配置 Milvus 向量数据库',
    'RAG 检索的最佳实践',
    'Agent 工作流的设计模式'
)

$durations = @()
for ($i = 1; $i -le 50; $i++) {
    $query = $queries[$i % $queries.Count]
    $body = @{ query = $query; knowledge_base_id = 52; top_k = 5 } | ConvertTo-Json
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)

    $start = Get-Date
    try {
        $r = Invoke-WebRequest -Uri "$PythonUrl/api/rag/debug/search" -Method Post -Headers $pyHeaders -Body $bodyBytes -UseBasicParsing -TimeoutSec 10
        $durations += ((Get-Date) - $start).TotalMilliseconds
    } catch {
        # 跳过失败请求
    }
}

if ($durations.Count -gt 0) {
    $avg = ($durations | Measure-Object -Average).Average
    $p50 = Measure-Percentile $durations 0.5
    $p95 = Measure-Percentile $durations 0.95
    $p99 = Measure-Percentile $durations 0.99
    Write-Host "请求数: $($durations.Count)" -ForegroundColor Green
    Write-Host "平均延迟: $([math]::Round($avg))ms" -ForegroundColor Green
    Write-Host "P50 延迟: $([math]::Round($p50))ms" -ForegroundColor Green
    Write-Host "P95 延迟: $([math]::Round($p95))ms" -ForegroundColor Green
    Write-Host "P99 延迟: $([math]::Round($p99))ms" -ForegroundColor Green
} else {
    Write-Host "[SKIP] 无可用知识库或检索失败" -ForegroundColor Yellow
}

# ── 3. 文档处理端到端 ─────────────────────────────────────────────────
Write-Host "`n==== 3. 文档处理端到端（上传→解析→向量化）====" -ForegroundColor Cyan

$testDoc = Join-Path $RepoRoot 'test-data\java-threads.md'
if (Test-Path $testDoc) {
    # 创建临时知识库
    $kb = Invoke-RestMethod -Uri "$BaseUrl/api/knowledge-base" -Method Post -Headers $headers -Body (@{name='_Benchmark_KB';description='性能测试'}|ConvertTo-Json) -ContentType 'application/json'
    $kbId = $kb.data.id

    $durations = @()
    for ($i = 1; $i -le 5; $i++) {
        Write-Host "  [$i/5] 上传并解析文档..." -ForegroundColor Yellow
        $start = Get-Date

        # 上传
        $upJson = curl.exe -s -X POST "$BaseUrl/api/document/upload" -H "satoken: $($login.data)" -F "file=@$testDoc" -F "title=Bench-$i" -F "knowledgeBaseId=$kbId"
        $up = $upJson | ConvertFrom-Json
        $docId = $up.data.id

        # 触发解析
        curl.exe -s -X POST "$BaseUrl/api/document/$docId/parse" -H "satoken: $($login.data)" | Out-Null

        # 轮询直到完成
        $timeout = 60
        $elapsed = 0
        while ($elapsed -lt $timeout) {
            Start-Sleep -Seconds 2
            $elapsed += 2
            $doc = (curl.exe -s "$BaseUrl/api/document/$docId" -H "satoken: $($login.data)") | ConvertFrom-Json
            if ($doc.data.status -eq 2) {
                $duration = ((Get-Date) - $start).TotalSeconds
                $durations += $duration
                Write-Host "    耗时: $([math]::Round($duration, 2))s" -ForegroundColor Green
                break
            }
            if ($doc.data.status -eq 3) {
                Write-Host "    [FAIL] 解析失败" -ForegroundColor Red
                break
            }
        }
    }

    if ($durations.Count -gt 0) {
        $avg = ($durations | Measure-Object -Average).Average
        $p50 = Measure-Percentile $durations 0.5
        $p95 = Measure-Percentile $durations 0.95
        Write-Host "平均耗时: $([math]::Round($avg, 2))s" -ForegroundColor Green
        Write-Host "P50 延迟: $([math]::Round($p50, 2))s" -ForegroundColor Green
        Write-Host "P95 延迟: $([math]::Round($p95, 2))s" -ForegroundColor Green
    }

    # 清理
    Invoke-RestMethod -Uri "$BaseUrl/api/knowledge-base/$kbId" -Method Delete -Headers $headers | Out-Null
} else {
    Write-Host "[SKIP] 缺少 test-data\java-threads.md" -ForegroundColor Yellow
}

# ── 4. 前端 Lighthouse（可选，需 Chrome）─────────────────────────────
Write-Host "`n==== 4. 前端性能（Lighthouse）====" -ForegroundColor Cyan
Write-Host "[SKIP] 需手动运行: npx lighthouse $FrontendUrl --output html" -ForegroundColor Yellow

# ── 汇总 ──────────────────────────────────────────────────────────────
Write-Host "`n==== 测试完成 ====" -ForegroundColor Cyan
Write-Host "基线报告已生成，建议保存到 docs/baselines/baseline-$(Get-Date -Format 'yyyyMMdd').txt"
Write-Host ""
