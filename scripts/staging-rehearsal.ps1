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
    [switch]$PruneVolumes,
    [string]$DindProxy = $env:DIND_PROXY
)

# 注意：不设 "Stop"。native 命令（docker）写 stderr 时会被 Stop 当作终止
# 错误抛出，即使 2>$null 也无法抑制。脚本统一用 $LASTEXITCODE 判断成败。
$ErrorActionPreference = "Continue"
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
    if (Select-String -Path $EnvFile -Pattern "^$k=" -Quiet) {
        $lines = Get-Content $EnvFile
        $lines = $lines | ForEach-Object {
            if ($_ -match "^$k=") { "$k=$($tlsFiles[$k])" } else { $_ }
        }
        Set-Content -Path $EnvFile -Value $lines
    } else {
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

# The runner uses root-level files as Compose secrets, while docker:dind
# requires its own /certs/{server,client} layout. Materialize copies without
# reissuing a previously generated CA/client certificate set.
$dindLayout = Join-Path $TlsDir "dind-certs"
$dindLayoutMissing = @(
    "server\ca.pem", "server\cert.pem", "server\key.pem",
    "client\ca.pem", "client\cert.pem", "client\key.pem"
) | Where-Object { -not (Test-Path (Join-Path $dindLayout $_)) }
if ($dindLayoutMissing.Count -gt 0) {
    Write-Host "补齐 docker:dind TLS 证书目录..."
    $genMounted = Join-Path (Split-Path $PSScriptRoot) "generate-runner-tls.sh"
    docker run --rm `
        --entrypoint /bin/sh `
        -v "${PSScriptRoot}:/work:ro" `
        -v "${TlsDir}:/out" `
        alpine/openssl:3.3.0 -c "cp /work/generate-runner-tls.sh /tmp/gen.sh && sh /tmp/gen.sh /out --dind-layout"
    if ($LASTEXITCODE -ne 0) { throw "无法补齐 docker:dind TLS 证书目录" }
}

function Test-DindReady {
    param([string]$CertPath)
    $previous = @{
        DOCKER_HOST       = $env:DOCKER_HOST
        DOCKER_TLS_VERIFY = $env:DOCKER_TLS_VERIFY
        DOCKER_CERT_PATH  = $env:DOCKER_CERT_PATH
    }
    try {
        $env:DOCKER_HOST = "tcp://127.0.0.1:2376"
        $env:DOCKER_TLS_VERIFY = "1"
        $env:DOCKER_CERT_PATH = $CertPath
        docker version --format '{{.Server.Version}}' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } finally {
        foreach ($key in $previous.Keys) {
            if ($null -eq $previous[$key]) { Remove-Item "Env:$key" -ErrorAction SilentlyContinue }
            else { Set-Item "Env:$key" $previous[$key] }
        }
    }
}

if ($DindProxy) {
    $DindProxy = $DindProxy -replace '://(127\.0\.0\.1|localhost)(?=[:/])', '://host.docker.internal'
}

# ── 3. 隔离 Docker Engine（演练用 dind）────────────────────────────────
$useDind = -not $NoDind
if ($NoDind) {
    # Do not let an earlier rehearsal make a no-Dind run appear healthy.
    # This container name is owned exclusively by this script.
    $existing = docker ps -a --format '{{.Names}}' | Select-String -Quiet $DindName
    if ($existing) { docker rm -f $DindName 2>$null | Out-Null }
}
if ($useDind) {
    $already = docker ps --format '{{.Names}}' | Select-String -Quiet $DindName
    if ($already) {
        Write-Host "[dind] 演练引擎已在运行：$DindName"
    } else {
        # dind 引擎走 TLS：docker:dind 用 DOCKER_TLS_CERTDIR 下的自管 CA
        # （server/{ca,cert,key}.pem），SAN 含 host.docker.internal/localhost/127.0.0.1，
        # 与 runner 客户端证书同 CA。runner 经 host.docker.internal:2376 访问。
        $DindCerts = $dindLayout
        if (-not (Test-Path (Join-Path $DindCerts "server\ca.pem"))) {
            Write-Warning "缺少 dind 引擎证书目录 $DindCerts\server（请先运行 generate-runner-tls.sh）。runner 将无法连引擎，预期 503。"
            $useDind = $false
        } else {
            Write-Host "[dind] 启动隔离演练引擎（docker:dind + TLS）..."
            $existing = docker ps -a --format '{{.Names}}' | Select-String -Quiet $DindName
            if ($existing) { docker rm -f $DindName 2>$null | Out-Null }
            $dindArgs = @('run', '-d', '--privileged', '--name', $DindName,
                '-p', '127.0.0.1:2376:2376',
                '-e', 'DOCKER_TLS_CERTDIR=/certs',
                '-v', "${DindCerts}:/certs:ro",
                'docker:dind')
            if ($DindProxy) {
                $dindArgs = @('run', '-d', '--privileged', '--name', $DindName,
                    '-p', '127.0.0.1:2376:2376',
                    '-e', 'DOCKER_TLS_CERTDIR=/certs',
                    '-e', "HTTP_PROXY=$DindProxy", '-e', "HTTPS_PROXY=$DindProxy",
                    '-e', 'NO_PROXY=localhost,127.0.0.1,host.docker.internal',
                    '-v', "${DindCerts}:/certs:ro",
                    'docker:dind')
            }
            & docker $dindArgs 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "无法启动 dind（嵌套虚拟化可能被禁）。runner 将无法连引擎，预期 503。"
                $useDind = $false
            } elseif (Test-DindReady -CertPath (Join-Path $DindCerts "client")) {
                Write-Host "[dind] 演练引擎已启动：$DindName（TLS 加密）"
            } else {
                Write-Warning "dind 已启动但 TLS 握手失败。runner 将无法连引擎，预期 503。"
                docker rm -f $DindName 2>$null | Out-Null
                $useDind = $false
            }
        }
    }
}

if ($useDind -and -not (Test-DindReady -CertPath (Join-Path $dindLayout "client"))) {
    Write-Warning "现有 dind 引擎 TLS 握手失败，runner 将无法连引擎，预期 503。"
    docker rm -f $DindName 2>$null | Out-Null
    $useDind = $false
}

# 让 dind 接入 compose 网络，runner 经 host.docker.internal 访问宿主映射端口。
if ($useDind) {
    $netName = "deploy_default"
    $netExists = $false
    docker network inspect $netName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $netExists = $true }
    if ($netExists) {
        docker network connect $netName $DindName 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host "[dind] 已接入网络 $netName" }
    } else {
        Write-Host "[dind] 网络 $netName 尚不存在，跳过显式接入（compose up 会自动创建）。"
    }
}

# The runner host is process-scoped below. Never persist a rehearsal endpoint
# in deploy/.env: a subsequent -NoDind run must not contact a real engine.
$runnerDockerHost = if ($useDind) {
    "tcp://host.docker.internal:2376"
} else {
    "tcp://127.0.0.1:2377"
}

# ── 4. 拉起全链路 ───────────────────────────────────────────────────────
Write-Host "==> 拉起 prod compose（首次会构建镜像，耗时较长）..."
Push-Location $Root
try {
    $previousRunnerDockerHost = $env:PLUGIN_RUNNER_DOCKER_HOST
    $env:PLUGIN_RUNNER_DOCKER_HOST = $runnerDockerHost
    docker compose -f $ComposeFile up -d --build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "::error::compose up 失败 rc=$LASTEXITCODE"
        docker compose -f $ComposeFile ps
        exit 1
    }
} finally {
    if ($null -eq $previousRunnerDockerHost) {
        Remove-Item Env:PLUGIN_RUNNER_DOCKER_HOST -ErrorAction SilentlyContinue
    } else {
        $env:PLUGIN_RUNNER_DOCKER_HOST = $previousRunnerDockerHost
    }
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
Write-Host "    frontend /          -> $(Probe http://127.0.0.1:80/)"

# runner 端口 9100 仅 expose 未发布到宿主，故在容器内探活
$runnerHealth = docker exec hfusionhub-plugin-runner sh -c "curl -s http://127.0.0.1:9100/health" 2>$null
Write-Host "    runner  /health     -> $runnerHealth"
$runnerConnected = $runnerHealth -match '"docker_connected":true'
if ($useDind -and -not $runnerConnected) {
    $fails.Add("plugin-runner-engine")
    Write-Host "    runner engine connection -> FAIL"
} elseif (-not $useDind -and $runnerConnected) {
    $fails.Add("plugin-runner-fail-closed")
    Write-Host "    runner fail-closed state -> FAIL"
}

if ($fails.Count -eq 0 -and $useDind) {
    Write-Host "结论：全链路健康（runner 已连演练引擎）。"
    exit 0
} elseif ($fails.Count -eq 0 -and (-not $useDind)) {
    Write-Host "结论：应用全链路 healthy，但 runner 未连隔离引擎（预期 503）。"
    Write-Host "      如需全绿，请提供真实 PLUGIN_RUNNER_DOCKER_HOST 或启用嵌套虚拟化。"
    exit 3
} else {
    Write-Host "结论：演练失败 —— 未 healthy: $($fails -join ', ')"
    docker compose -f $ComposeFile logs --tail=50 $fails
    exit 1
}
