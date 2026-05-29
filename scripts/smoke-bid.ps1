# smoke-bid.ps1 — 招投标垂直化冒烟测试
#
# 覆盖：登录 → /demo/import-bid 一键导入招标文件知识库 + 示例投标项目 →
#       投标项目列表/详情 → 状态推进 →（可选）触发解读（需 LLM 可用）。
# 任一必需项失败时退出码非 0。
#
# 用法：
#   .\scripts\smoke-bid.ps1                                  # 完整（含解读，需 LLM 可用）
#   .\scripts\smoke-bid.ps1 -SkipInterpret                   # 仅数据链路，不触发解读
#   .\scripts\smoke-bid.ps1 -BaseUrl http://localhost:8080 -PythonUrl http://localhost:9000
#
# 前置：服务已启动；docker\.env 含 ADMIN_PASSWORD。

param(
    [switch]$SkipInterpret,
    [string]$BaseUrl = 'http://localhost:8080',
    [string]$PythonUrl = 'http://localhost:9000'
)

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $RepoRoot 'docker\.env'

function Get-EnvVal($key) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$key=" } | Select-Object -First 1
    if ($line) { return ($line -split '=', 2)[1].Trim() }
    return ''
}

$script:Pass = 0
$script:Fail = 0
$script:Failures = @()

function Test-Ok {
    param([string]$Name, [bool]$Ok, [string]$Detail = '')
    if ($Ok) {
        $script:Pass++
        Write-Host "[PASS] $Name" -ForegroundColor Green
    } else {
        $script:Fail++
        $script:Failures += "$Name$($(if ($Detail) { " - $Detail" } else { '' }))"
        Write-Host "[FAIL] $Name$($(if ($Detail) { " - $Detail" } else { '' }))" -ForegroundColor Red
    }
}

function Invoke-Api {
    param([string]$Method, [string]$Path, [hashtable]$Headers = @{}, $Body = $null, [int]$Timeout = 25)
    try {
        if ($Body -ne $null) {
            return Invoke-RestMethod -Uri "$BaseUrl/api$Path" -Method $Method -Headers $Headers -Body $Body -ContentType 'application/json; charset=utf-8' -TimeoutSec $Timeout
        }
        return Invoke-RestMethod -Uri "$BaseUrl/api$Path" -Method $Method -Headers $Headers -TimeoutSec $Timeout
    } catch {
        return $null
    }
}

Write-Host "==== 招投标垂直化冒烟测试 ====" -ForegroundColor Cyan
Write-Host "Java: $BaseUrl | Python: $PythonUrl"

# ── 0. 前置：登录 ───────────────────────────────────────────────────────
$adminPw = Get-EnvVal 'ADMIN_PASSWORD'
if (-not $adminPw) {
    Write-Host "[SKIP] docker\.env 缺少 ADMIN_PASSWORD，无法测试需要登录的 API" -ForegroundColor Yellow
    exit 1
}
$login = $null
try {
    $login = Invoke-RestMethod -Uri "$BaseUrl/api/user/login" -Method Post -Body (@{ username = 'admin'; password = $adminPw } | ConvertTo-Json) -ContentType 'application/json' -TimeoutSec 20
} catch { }
Test-Ok '登录' ($login -ne $null -and $login.code -eq 200 -and $login.data)
if (-not $login.data) { exit 1 }
$headers = @{ satoken = $login.data }

# ── 1. 一键导入招投标演示环境 ───────────────────────────────────────────
$import = Invoke-Api 'POST' '/demo/import-bid' $headers
Test-Ok '演示导入-import-bid' ($import -ne $null -and $import.code -eq 200 -and $import.data.knowledgeBaseId -gt 0)
if ($import.code -eq 200) {
    Test-Ok '演示导入-招标文件4篇' ($import.data.importedCount + $import.data.skippedCount -eq 4) "imported=$($import.data.importedCount), skipped=$($import.data.skippedCount)"
    $bidSection = $import.data.sections | Where-Object { $_.section -eq 'bid_project' } | Select-Object -First 1
    Test-Ok '演示导入-示例投标项目' ($null -ne $bidSection -and $bidSection.importedCount -ge 0) "imported=$($bidSection.importedCount), skipped=$($bidSection.skippedCount)"
    Write-Host "  $($import.data.message)" -ForegroundColor DarkGray
}

# ── 2. 投标项目列表 ─────────────────────────────────────────────────────
$list = Invoke-Api 'GET' '/bid/project/list?page=1&pageSize=10' $headers
Test-Ok '投标项目-列表' ($list -ne $null -and $list.code -eq 200)
$demoProject = $null
if ($list -ne $null -and $list.data -and $list.data.records) {
    $demoProject = $list.data.records | Where-Object { $_.title -like '*滨海园区*' } | Select-Object -First 1
}
Test-Ok '投标项目-示例项目存在' ($null -ne $demoProject) "title=$($demoProject.title)"
if (-not $demoProject) { exit 1 }
$projectId = $demoProject.id

# ── 3. 详情 + 状态推进 ─────────────────────────────────────────────────
$detail = Invoke-Api 'GET' "/bid/project/$projectId/detail" $headers
Test-Ok '投标项目-详情' ($detail -ne $null -and $detail.code -eq 200 -and $null -ne $detail.data.project)
Test-Ok '投标项目-详情结构(要素/评分/需求)' (
    $detail.data.elements -is [System.Array] -and
    $detail.data.scoringMethods -is [System.Array] -and
    $detail.data.requirements -is [System.Array]
)

$statusUpdate = Invoke-Api 'PUT' "/bid/project/$projectId/status?status=requirements" $headers
Test-Ok '投标项目-状态推进(→requirements)' ($statusUpdate -ne $null -and $statusUpdate.code -eq 200 -and $statusUpdate.data.status -eq 'requirements')
$statusRestore = Invoke-Api 'PUT' "/bid/project/$projectId/status?status=interpreting" $headers
Test-Ok '投标项目-状态回退(→interpreting)' ($statusRestore -ne $null -and $statusRestore.code -eq 200)

# ── 4. 触发解读（需 LLM；无有效 key 时按最佳努力，仅告警）──────────────
if (-not $SkipInterpret) {
    $pyVenv = Join-Path $RepoRoot 'python-ai\.venv\Scripts\python.exe'
    $pyDir = Join-Path $RepoRoot 'python-ai'
    $llmReady = $false
    if (Test-Path $pyVenv) {
        $probe = @"
import os
os.chdir(r'$pyDir')
from app.utils.config import config
from app.core.llm.deepseek_llm import _is_placeholder_key
key = config.DEEPSEEK_API_KEY or ''
print('DEEPSEEK_VALID=' + str(bool(key and not _is_placeholder_key(key))))
"@
        try {
            $probeOut = & $pyVenv -c $probe 2>&1
            $dsValid = ($probeOut | Where-Object { $_ -match '^DEEPSEEK_VALID=' }) -replace '^DEEPSEEK_VALID=', ''
            $llmReady = $dsValid -eq 'True'
        } catch { $llmReady = $false }
    }
    Write-Host "── 触发解读（LLM 可用: $llmReady）──" -ForegroundColor Cyan
    $interpret = Invoke-Api 'POST' "/bid/project/$projectId/interpret" $headers $null 120
    if ($interpret -ne $null -and $interpret.code -eq 200) {
        Test-Ok '解读-触发成功' $true "需求数=$($interpret.data.requirements.Count), 要素数=$($interpret.data.elements.Count)"
        Test-Ok '解读-需求清单非空' ($interpret.data.requirements.Count -gt 0)
        # 需求状态推进（人工确认）
        if ($interpret.data.requirements.Count -gt 0) {
            $req = $interpret.data.requirements[0]
            $reqUpdate = Invoke-Api 'PUT' "/bid/project/$projectId/requirements/$($req.id)/status?status=checked" $headers
            Test-Ok '需求-状态确认(→checked)' ($reqUpdate -ne $null -and $reqUpdate.code -eq 200)
        }
    } else {
        if ($llmReady) {
            Test-Ok '解读-触发成功' $false "已配置 LLM 但解读失败"
        } else {
            Write-Host "[WARN] 未检测到有效 DeepSeek key，解读需 LLM 可用；已跳过解读链路（数据链路仍全绿）" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[INFO] -SkipInterpret 已指定，跳过解读链路" -ForegroundColor DarkGray
}

# ── 汇总 ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==== 结果: $($script:Pass) PASS / $($script:Fail) FAIL ====" -ForegroundColor $(if ($script:Fail -eq 0) { 'Green' } else { 'Red' })
if ($script:Failures.Count -gt 0) {
    Write-Host "失败项:" -ForegroundColor Red
    $script:Failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
exit 0
