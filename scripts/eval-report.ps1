#!/usr/bin/env pwsh
# eval-report.ps1 — 运行离线评测门禁并输出 JSON + Markdown 报告（第二十二批）
#
# 封装 python-ai/scripts/eval_offline.py（确定性合成索引上的冻结评测集）：
#   - 默认: 运行并与已存基线对比，回归/不达标时退出码非 0
#   - -UpdateBaseline: 把当前结果记为新基线
#   - -MinimumRecall / -MinimumNdcg: 自定义门槛
#
# 报告输出: python-ai/evaluation/reports/（JSON + Markdown）
#
# 用法:
#   .\scripts\eval-report.ps1
#   .\scripts\eval-report.ps1 -UpdateBaseline
#   .\scripts\eval-report.ps1 -MinimumRecall 0.90 -MinimumNdcg 0.80

param(
    [string]$MinimumRecall = '',
    [string]$MinimumNdcg = '',
    [switch]$UpdateBaseline
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pyExe = Join-Path $repoRoot 'python-ai\.venv\Scripts\python.exe'
if (-not (Test-Path $pyExe)) { $pyExe = 'python' }

$args = @('scripts/eval_offline.py')
if ($UpdateBaseline) { $args += '--update-baseline' }
if ($MinimumRecall) { $args += @('--minimum-recall', $MinimumRecall) }
if ($MinimumNdcg) { $args += @('--minimum-ndcg', $MinimumNdcg) }

Push-Location (Join-Path $repoRoot 'python-ai')
try {
    & $pyExe @args
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ''
if ($code -eq 0) {
    Write-Host '✓ 评测通过。报告目录: python-ai\evaluation\reports\' -ForegroundColor Green
} else {
    Write-Host "✗ 评测未通过（退出码 $code）——报告与回归明细见 python-ai\evaluation\reports\" -ForegroundColor Red
}
exit $code
