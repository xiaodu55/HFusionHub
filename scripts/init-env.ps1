<#
.SYNOPSIS
    生成/刷新 HFusionHub 全部本地环境配置文件（docker/.env、python-ai/.env、deploy/.env），
    使用加密强度随机数自动填充密码与令牌，避免弱口令、占位符或真实密钥进入部署。

.DESCRIPTION
    - docker/.env     : MySQL / Redis / MinIO / Plugin Runner / Admin 强随机口令
    - python-ai/.env  : 更新 PYTHON_AI_INTERNAL_TOKEN / CALLBACK_SECRET 与 docker/.env 保持一致
    - deploy/.env     : 生产部署密钥（从 deploy/.env.example 模板生成）
    生成后仍需手动填写的内容会打印提示（如 DEEPSEEK_API_KEY、Runner TLS 证书路径）。

.PARAMETER Reset
    强制重新生成全部口令（默认仅当文件缺失时生成）。

.EXAMPLE
    .\scripts\init-env.ps1
    .\scripts\init-env.ps1 -Reset
#>
param([switch]$Reset)
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot

function New-RandomString([int]$Length = 24) {
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

function Update-KeyValue([string]$FilePath, [hashtable]$Updates) {
    if (-not (Test-Path $FilePath)) { throw "文件不存在: $FilePath" }
    $content = Get-Content $FilePath -Raw
    foreach ($key in $Updates.Keys) {
        if ($content -match "(?m)^$([regex]::Escape($key))=") {
            $content = $content -replace "(?m)^$([regex]::Escape($key))=.*$", "$key=$($Updates[$key])"
        } else {
            $content = $content.TrimEnd() + "`n$key=$($Updates[$key])`n"
        }
    }
    Set-Content -Path $FilePath -Value $content -Encoding utf8
}

function Ensure-EnvFile([string]$Source, [string]$Target, [switch]$Force) {
    if ((Test-Path $Target) -and -not $Force) {
        Write-Host "  [skip] $Target 已存在（使用 -Reset 重新生成）"
        return $false
    }
    Copy-Item $Source $Target -Force
    Write-Host "  [ok] 已创建 $Target"
    return $true
}

Write-Host "==> 生成 HFusionHub 环境配置（仓库根: $repoRoot）"

# 1) 生成三份共用的随机令牌（保证 Java <-> Python 一致）
$internalToken = New-RandomString 32
$callbackSecret = New-RandomString 32
$adminPass = New-RandomString 16

# 2) docker/.env（基础设施）
$dockerEnv = Join-Path $repoRoot 'docker\.env'
$dockerExample = Join-Path $repoRoot 'docker\.env.example'
if ((Test-Path $dockerEnv) -and -not $Reset) {
    Write-Host "  [skip] docker/.env 已存在（使用 -Reset 重新生成）"
} else {
    if (-not (Test-Path $dockerEnv)) {
        if (-not (Test-Path $dockerExample)) { throw "缺少模板: $dockerExample" }
        Copy-Item $dockerExample $dockerEnv
    }
    Update-KeyValue $dockerEnv @{
        'MYSQL_ROOT_PASSWORD'   = New-RandomString 20
        'MYSQL_PASSWORD'        = New-RandomString 20
        'REDIS_PASSWORD'        = New-RandomString 20
        'MINIO_ROOT_PASSWORD'   = New-RandomString 20
        'PLUGIN_RUNNER_TOKEN'   = New-RandomString 32
        'ADMIN_PASSWORD'        = $adminPass
        'PYTHON_AI_INTERNAL_TOKEN' = $internalToken
        'CALLBACK_SECRET'       = $callbackSecret
    }
    Write-Host "  [ok] docker/.env 已更新为随机强口令"
}

# 3) python-ai/.env（更新共享令牌；其余配置保持不变）
$pythonEnv = Join-Path $repoRoot 'python-ai\.env'
$pythonExample = Join-Path $repoRoot 'python-ai\.env.example'
if ((Test-Path $pythonEnv) -and -not $Reset) {
    Write-Host "  [skip] python-ai/.env 已存在（使用 -Reset 重新生成）"
} else {
    Ensure-EnvFile $pythonExample $pythonEnv -Force:$Reset | Out-Null
    Update-KeyValue $pythonEnv @{
        'PYTHON_AI_INTERNAL_TOKEN' = $internalToken
        'CALLBACK_SECRET'       = $callbackSecret
    }
    Write-Host "  [ok] python-ai/.env 令牌与 docker/.env 保持一致"
}

# 4) deploy/.env（生产部署；从示例模板生成）
$deployEnv = Join-Path $repoRoot 'deploy\.env'
$deployExample = Join-Path $repoRoot 'deploy\.env.example'
if ((Test-Path $deployEnv) -and -not $Reset) {
    Write-Host "  [skip] deploy/.env 已存在（使用 -Reset 重新生成）"
} else {
    if (-not (Test-Path $deployEnv)) {
        if (-not (Test-Path $deployExample)) { throw "缺少模板: $deployExample" }
        Copy-Item $deployExample $deployEnv
    }
    Update-KeyValue $deployEnv @{
        'MYSQL_ROOT_PASSWORD'   = New-RandomString 20
        'MYSQL_PASSWORD'        = New-RandomString 20
        'PYTHON_AI_INTERNAL_TOKEN' = $internalToken
        'CALLBACK_SECRET'       = $callbackSecret
        'ADMIN_PASSWORD'        = $adminPass
        'PLUGIN_RUNNER_TOKEN'   = New-RandomString 32
    }
    Write-Host "  [ok] deploy/.env 已生成"
}

Write-Host ""
Write-Host "==> 完成。还需手动填写以下内容（脚本无法猜测）："
Write-Host "  1. python-ai/.env 与 deploy/.env 中的 DEEPSEEK_API_KEY（在模型供应商控制台获取；旧 Key 若曾泄露请先轮换）"
Write-Host "  2. deploy/.env 中的 PLUGIN_RUNNER_DOCKER_HOST 与 3 个 Runner TLS 证书路径"
Write-Host "     （先运行 bash scripts/generate-runner-tls.sh deploy/runner-tls）"
Write-Host "  3. 管理员账号：admin / $adminPass（由 ADMIN_PASSWORD 决定，可自行修改后重启）"
Write-Host ""
Write-Host "下一步：运行 .\scripts\setup.ps1 一键启动（-FullStack 全部容器化）。"
