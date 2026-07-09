# run-all-tests.ps1 — HFusionHub 本地全量测试兜底（CI 恢复前的 PR 门禁替代）
#
# 背景：GitHub Actions 因账户计费问题全部 job 即败（见 TODO.md P0-0），PR 门禁实际失效。
# 在恢复前，合并前需本地跑完全部质量门禁——本脚本将四道门禁串成一键流程：
#   1. 静态一致性检查（scripts/static-checks.py：测试计数、tenant 列、内部 token 键名）
#   2. Java 全量测试（mvn test）
#   3. Python 全量测试（pytest -q tests）
#   4. 前端构建 + 单测（npm run build && npx vitest run）
#
# 用法：
#   .\scripts\run-all-tests.ps1                     # 全部四道门禁
#   .\scripts\run-all-tests.ps1 -SkipFrontend       # 跳过前端
#   .\scripts\run-all-tests.ps1 -SkipJava -SkipPython   # 仅静态检查
#
# 退出码：任一未跳过门禁失败 → 1；全部通过 → 0。

param(
    [switch]$SkipStatic,
    [switch]$SkipJava,
    [switch]$SkipPython,
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$RepoRoot = Split-Path -Parent $PSScriptRoot

$script:Results = @()
$script:FailCount = 0

function Invoke-Gate {
    param(
        [string]$Name,
        [scriptblock]$Action,
        [string]$WorkingDir
    )
    Write-Host ""
    Write-Host "==> [$Name] 开始（$WorkingDir）" -ForegroundColor Cyan
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    & $Action
    $exit = $LASTEXITCODE
    $sw.Stop()
    $minutes = [math]::Round($sw.Elapsed.TotalMinutes, 1)
    if ($exit -eq 0) {
        Write-Host "==> [$Name] PASS（$minutes min）" -ForegroundColor Green
        $script:Results += [pscustomobject]@{ Gate = $Name; Result = 'PASS'; Duration = "$minutes min" }
    } else {
        Write-Host "==> [$Name] FAIL（exit=$exit，$minutes min）" -ForegroundColor Red
        $script:Results += [pscustomobject]@{ Gate = $Name; Result = 'FAIL'; Duration = "$minutes min" }
        $script:FailCount++
    }
}

function Get-PythonExe {
    $venvPython = Join-Path $RepoRoot 'python-ai\.venv\Scripts\python.exe'
    if (Test-Path $venvPython) { return $venvPython }
    return 'python'
}

# ── 1. 静态一致性检查 ─────────────────────────────────────────────
if (-not $SkipStatic) {
    $pyExe = Get-PythonExe
    Invoke-Gate -Name '静态一致性 static-checks' -WorkingDir 'scripts' -Action {
        & $pyExe (Join-Path $RepoRoot 'scripts\static-checks.py') --test-counts --tenant-columns --internal-token-keys
        if ($LASTEXITCODE -ne 0) {
            # 完整模式兜底（个别参数子集失败时以全量为准）
            & $pyExe (Join-Path $RepoRoot 'scripts\static-checks.py')
        }
    }
}

# ── 2. Java 全量测试 ──────────────────────────────────────────────
if (-not $SkipJava) {
    Invoke-Gate -Name 'Java mvn test' -WorkingDir 'java-backend' -Action {
        Push-Location (Join-Path $RepoRoot 'java-backend')
        try { mvn test -q; $global:LASTEXITCODE = $LASTEXITCODE } finally { Pop-Location }
    }
}

# ── 3. Python 全量测试 ────────────────────────────────────────────
if (-not $SkipPython) {
    $pyExe = Get-PythonExe
    Invoke-Gate -Name 'Python pytest' -WorkingDir 'python-ai' -Action {
        Push-Location (Join-Path $RepoRoot 'python-ai')
        try {
            & $pyExe -m pytest -q tests
            $global:LASTEXITCODE = $LASTEXITCODE
        } finally { Pop-Location }
    }
}

# ── 4. 前端构建 + 单测 ────────────────────────────────────────────
if (-not $SkipFrontend) {
    Invoke-Gate -Name '前端 build' -WorkingDir 'hfusionhub-frontend' -Action {
        Push-Location (Join-Path $RepoRoot 'hfusionhub-frontend')
        try { npm run build; $global:LASTEXITCODE = $LASTEXITCODE } finally { Pop-Location }
    }
    if ($script:FailCount -eq 0) {
        Invoke-Gate -Name '前端 vitest' -WorkingDir 'hfusionhub-frontend' -Action {
            Push-Location (Join-Path $RepoRoot 'hfusionhub-frontend')
            try { npx vitest run; $global:LASTEXITCODE = $LASTEXITCODE } finally { Pop-Location }
        }
    }
}

# ── 汇总 ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==== 本地全量测试结果 ====" -ForegroundColor Cyan
$script:Results | Format-Table -AutoSize | Out-Host
if ($script:FailCount -gt 0) {
    Write-Host "==== 结果: $($script:Results.Count - $script:FailCount) PASS / $script:FailCount FAIL ====" -ForegroundColor Red
    Write-Host "CI 恢复前禁止合并：修复失败门禁后重跑。" -ForegroundColor Yellow
    exit 1
}
Write-Host "==== 结果: $($script:Results.Count) PASS / 0 FAIL ====" -ForegroundColor Green
Write-Host "四道门禁全绿，可合并（CI 恢复后仍以 CI 为准）。" -ForegroundColor Green
exit 0
