<#
.SYNOPSIS
    HFusionHub Staging 演练（Windows PowerShell 版）

.DESCRIPTION
    用 deploy/docker-compose.prod.yml 在隔离环境拉全链路，验证
    Java / Python / Milvus / plugin-runner / frontend 全部健康。

    等价于 scripts/staging-rehearsal.sh，专供 Windows 本机（无需 bash）。
    健康状态一律通过 `docker compose ps --format` 按 Compose 服务名读取，
    绝不手拼容器名。

.PARAMETER NoDind
    不使用本机 docker:dind 演练引擎，runner 预期 503。

.PARAMETER Down
    停止演练（默认保留数据卷）。

.PARAMETER PruneVolumes
    与 -Down 搭配，删除数据卷。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/staging-rehearsal.ps1
    powershell -ExecutionPolicy Bypass -File scripts/staging-rehearsal.ps1 -NoDind
    powershell -ExecutionPolicy Bypass -File scripts/staging-rehearsal.ps1 -Down -PruneVolumes

    退出码：0=全链路 healthy(含 runner 连引擎)；3=应用全链 healthy 但 runner 503；
            1=存在非 runner 服务未 healthy。
#>
[CmdletBinding()]
param(
    [switch]$NoDind,
    [switch]$Down,
    [switch]$PruneVolumes
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Root "deploy\docker-compose.prod.yml"
$EnvFile = Join-Path $Root "deploy\.env"
$TlsDir = Join-Path $Root "deploy\runner-tls"
$DindName = "hfusionhub-rehearsal-dind"

function Assert-Tool {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "缺少命令: $Name"
    }
}
Assert-Tool docker
docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "docker compose 插件不可用" }

# ── Down ────────────────────────────────────────────────────────────────
if ($Down) {
    $extra = if ($PruneVolumes) { "-v" } else { "" }
    Push-Location $Root
    try {
        docker compose -f $ComposeFile down $extra --remove-orphans
    } finally {
        Pop-Location
    }
    if (docker ps -a --format '{{.Names}}' | Select-String -Quiet $DindName) {
        docker rm -f $DindName | Out-Null
        Write-Host "演练 dind 引擎已移除"
    }
    Write-Host "staging 环境已停止（数据卷默认保留；需删除请加 -PruneVolumes）。"
    exit 0
}

# ── 1. .env ─────────────────────────────────────────────────────────────
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Root "deploy\.env.example") $EnvFile
    Write-Host "已从 .env.example 复制 deploy\.env（请确认密钥已替换）"
}

function Get-RandomHex {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Ensure-EnvKey {
    param([string]$Name)
    if (-not (Select-String -Path $EnvFile -Pattern "^$Name=[^ ]+" -Quiet)) {
        Add-Content -Path $EnvFile -Value "$Name=$(Get-RandomHex)"
        Write-Host "已为 $Name 写入随机占位值"
    }
}
foreach ($k in @("MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD", "PYTHON_AI_INTERNAL_TOKEN",
                 "CALLBACK_SECRET", "ADMIN_PASSWORD", "PLUGIN_RUNNER_TOKEN", "DEEPSEEK_API_KEY")) {
    Ensure-EnvKey -Name $k
}

# TLS 证书文件路径必须以绝对路径写入 .env（compose 的 file: secret 相对
# project-directory 解析，相对路径会指向 deploy/deploy/... 而找不到）。
$tlsFiles = @{
    "PLUGIN_RUNNER_CA_CERT_FILE"        = (Join-Path $TlsDir "ca.pem")
    "PLUGIN_RUNNER_CLIENT_CERT_FILE"    = (Join-Path $TlsDir "cert.pem")
    "PLUGIN_RUNNER_CLIENT_KEY_FILE"     = (Join-Path $TlsDir "key.pem")
}
foreach ($k in $tlsFiles.Keys) {
    if (-not (Select-String -Path $EnvFile -Pattern "^$k=[^ ]+" -Quiet)) {
        Add-Content -Path $EnvFile -Value "$k=$($tlsFiles[$k])"
        Write-Host "已为 $k 写入绝对路径 $($tlsFiles[$k])"
    }
}

# ── 2. Runner TLS 证书 ──────────────────────────────────────────────────
$tlsMissing = @("ca.pem", "cert.pem", "key.pem") | Where-Object {
    -not (Test-Path (Join-Path $TlsDir $_))
}
if ($tlsMissing.Count -gt 0) {
    New-Item -ItemType Directory -Force -Path $TlsDir | Out-Null
    Write-Host "生成 Runner TLS 证书到 $TlsDir（本机无 openssl 时用 alpine/openssl 容器）..."
    $genMounted = Join-Path (Split-Path $PSScriptRoot) "generate-runner-tls.sh"
    docker run --rm `
        --entrypoint /bin/sh `
        -v "${PSScriptRoot}:/work:ro" `
        -v "${TlsDir}:/out" `
        alpine/openssl:3.3.0 -c "mkdir -p /out && cp /work/generate-runner-tls.sh /tmp/gen.sh && sh /tmp/gen.sh /out"
    if ($LASTEXITCODE -ne 0) { throw "无法生成 TLS 证书" }
}

# ── 3. 隔离 Docker Engine（演练用 dind）────────────────────────────────
$useDind = -not $NoDind
if ($useDind) {
    $already = docker ps --format '{{.Names}}' | Select-String -Quiet $DindName
    if ($already) {
        Write-Host "[dind] 演练引擎已在运行：$DindName"
    } else {
        Write-Host "[dind] 启动隔离演练引擎（docker:dind）..."
        docker rm -f $DindName 2>$null | Out-Null
        docker run -d --privileged --name $DindName -p 127.0.0.1:2376:2376 `
            docker:dind --host=tcp://0.0.0.0:2376 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "无法启动 dind（嵌套虚拟化可能被禁）。runner 将无法连引擎，预期 503。"
            $useDind = $false
        } else {
            Write-Host "[dind] 演练引擎已启动：$DindName"
        }
    }
}

# DOCKER_HOST 注入（生产由真实隔离引擎地址覆盖）
if ($useDind) {
    $set = @{
        PLUGIN_RUNNER_DOCKER_HOST      = "tcp://host.docker.internal:2376"
        PLUGIN_RUNNER_CA_CERT_FILE     = Join-Path $TlsDir "ca.pem"
        PLUGIN_RUNNER_CLIENT_CERT_FILE = Join-Path $TlsDir "cert.pem"
        PLUGIN_RUNNER_CLIENT_KEY_FILE  = Join-Path $TlsDir "key.pem"
    }
    foreach ($k in $set.Keys) {
        if (Select-String -Path $EnvFile -Pattern "^$k=" -Quiet) {
            $lines = Get-Content $EnvFile
            $lines = $lines | ForEach-Object {
                if ($_ -match "^$k=") { "$k=$($set[$k])" } else { $_ }
            }
            Set-Content -Path $EnvFile -Value $lines
        } else {
            Add-Content -Path $EnvFile -Value "$k=$($set[$k])"
        }
    }
}

# ── 4. 拉起全链路 ───────────────────────────────────────────────────────
Write-Host "==> 拉起 prod compose（首次会构建镜像，耗时较长）..."
Push-Location $Root
try {
    docker compose -f $ComposeFile up -d --build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "::error::compose up 失败 rc=$LASTEXITCODE"
        docker compose -f $ComposeFile ps
        exit 1
    }
} finally {
    Pop-Location
}

# ── 5. 健康校验 ─────────────────────────────────────────────────────────
$Services = @("mysql8", "redis7", "milvus", "java-backend", "plugin-runner", "python-ai", "frontend")

function Get-ServiceHealth {
    param([string]$Service)
    $line = docker compose -f $ComposeFile ps --format '{{.Service}}|{{.Health}}' |
        Where-Object { $_ -like "$Service|*" } | Select-Object -First 1
    if (-not $line) { return "" }
    return $line.Substring($line.IndexOf("|") + 1)
}

function Wait-Healthy {
    param([string]$Service, [int]$Tries = 60)
    for ($i = 0; $i -lt $Tries; $i++) {
        if ((Get-ServiceHealth -Service $Service) -eq "healthy") { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}

$fails = [System.Collections.Generic.List[string]]::new()
foreach ($svc in $Services) {
    Write-Host -NoNewline "[health] waiting $svc ..."
    if (Wait-Healthy -Service $svc) {
        Write-Host " OK"
    } else {
        $h = Get-ServiceHealth -Service $svc
        Write-Host " FAIL(health=$([string]$h))"
        $fails.Add($svc)
    }
}

# ── 6. 报告 ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "===== Staging 演练报告 ====="
foreach ($svc in $Services) {
    $h = Get-ServiceHealth -Service $svc
    Write-Host "  $svc : $h"
}

function Probe {
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return $r.StatusCode
    } catch {
        return "DOWN"
    }
}
Write-Host ""
Write-Host "  端点探活:"
Write-Host "    java    /api/health -> $(Probe http://127.0.0.1:8080/api/health)"
Write-Host "    python  /ready      -> $(Probe http://127.0.0.1:9000/ready)"
Write-Host "    runner  /health     -> $(Probe http://127.0.0.1:9100/health)"
Write-Host "    frontend /          -> $(Probe http://127.0.0.1:80/)"

if ($fails.Count -eq 0 -and (-not $NoDind)) {
    Write-Host "结论：全链路健康（runner 已连演练引擎）。"
    exit 0
} elseif ($fails.Count -eq 0 -and $NoDind) {
    Write-Host "结论：应用全链路 healthy，但 runner 未连隔离引擎（预期 503）。"
    Write-Host "      如需全绿，请提供真实 PLUGIN_RUNNER_DOCKER_HOST 或启用嵌套虚拟化。"
    exit 3
} else {
    Write-Host "结论：演练失败 —— 未 healthy: $($fails -join ', ')"
    docker compose -f $ComposeFile logs --tail=50 $fails
    exit 1
}
