#restart-modules.ps1
# Restart HFusionHub dev modules safely.
#
# Safety rules:
#   - A process is only killed if it can be proven to belong to THIS repository.
#     Ownership is proven ONLY if the process executable path or command line
#     references the repo root. Loose pattern matches (uvicorn app:app, -m
#     app.main, spring-boot:run) are intentionally NOT used, so an unrelated
#     service can never be misclassified. If ownership cannot be proven, we
#     refuse to kill it unless -Force is passed.
#   - Each module starts with the project virtual environment (where one exists)
#     and loads environment/config from docker\.env.
#   - After starting, we poll the module's health endpoint. If it does not
#     become healthy within the timeout, the script exits non-zero.
#
# Usage:
#   .\scripts\restart-modules.ps1 -Modules java,python,runner
#   .\scripts\restart-modules.ps1 -Modules python
#   .\scripts\restart-modules.ps1 -Modules python -NoStart
#   .\scripts\restart-modules.ps1 -Modules python -Force
#
# Ports: java=8080, python=9000, runner=9100.

param(
    [string[]]$Modules = @('java', 'python', 'runner'),
    [switch]$NoStart,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# -File 模式下 `-Modules java,python` 会被绑定成单个字符串 'java,python'
# （PowerShell 5.1 不会像 -Command 那样把逗号拆成数组），导致 ContainsKey
# 全 miss、模块被静默跳过还误报 healthy。这里统一归一化成数组。
$Modules = $Modules | ForEach-Object { $_ -split ',' } | Where-Object { $_ }

$RepoRoot = Split-Path -Parent $PSScriptRoot
$modulePorts = @{
    java   = 8080
    python = 9000
    runner = 9100
}

# java 的 actuator 已移至独立管理端口 9092（第十五轮 P0-8，/api 上下文之外）
$healthChecks = @{
    java   = 'http://localhost:9092/actuator/health'
    python = 'http://localhost:9000/health'
    runner = 'http://localhost:9100/health'
}

function Load-EnvFile {
    $envFile = Join-Path $RepoRoot 'docker\.env'
    if (-not (Test-Path $envFile)) { return }
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
            $idx = $line.IndexOf('=')
            $key = $line.Substring(0, $idx).Trim()
            $val = $line.Substring($idx + 1).Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                [Environment]::SetEnvironmentVariable($key, $val, 'Process')
            }
        }
    }
    # compose 侧变量名 → Spring Boot 期望变量名（docker\.env 用 MYSQL_*/MINIO_ROOT_*，
    # application.yml 读 DB_PASSWORD/MINIO_ACCESS_KEY/MINIO_SECRET_KEY）。
    # 仅在目标变量未显式设置时回退映射，显式设置优先。
    $map = @{
        'MYSQL_PASSWORD'         = 'DB_PASSWORD'
        'MINIO_ROOT_USER'        = 'MINIO_ACCESS_KEY'
        'MINIO_ROOT_PASSWORD'    = 'MINIO_SECRET_KEY'
    }
    foreach ($k in $map.Keys) {
        $src = [Environment]::GetEnvironmentVariable($k, 'Process')
        $dst = $map[$k]
        if ($src -and -not [Environment]::GetEnvironmentVariable($dst, 'Process')) {
            [Environment]::SetEnvironmentVariable($dst, $src, 'Process')
        }
    }
}

function Test-ProcessBelongsToRepo {
    param($Process)
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$($Process.Id)" -ErrorAction Stop).CommandLine
        if ($cmdline -and $cmdline.Contains($RepoRoot)) { return $true }
    } catch { }
    try {
        $procDir = $Process.Path
        if ($procDir -and $procDir.Contains($RepoRoot)) { return $true }
    } catch { }
    return $false
}

function Test-DockerManagedProcess {
    param($Process)
    # Docker Desktop 的端口映射监听进程。命中即视为「端口由 compose 容器占用」，
    # 提示跳过而不是误判为未知进程后保守退出。
    $dockerNames = @('com.docker.backend', 'vpnkit', 'docker-desktop', 'com.docker.service')
    foreach ($name in $dockerNames) {
        if ($Process.ProcessName -like "$name*") { return $true }
    }
    return $false
}

function Stop-PortProcess {
    param([int]$Port)
    # Returns $true if the port is free (or was released) and safe to start on;
    # $false if it is held by an external process and this module should be skipped.
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $procId = $c.OwningProcess
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if (-not $proc) { continue }

        if (Test-ProcessBelongsToRepo -Process $proc) {
            Write-Host "[kill] port $Port -> PID $procId ($($proc.ProcessName)) [repo-owned]"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
        elseif ($Force) {
            Write-Warning "[kill] port $Port -> PID $procId ($($proc.ProcessName)) NOT repo-owned; killing due to -Force"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
        elseif (Test-DockerManagedProcess -Process $proc) {
            # 端口被 Docker compose 容器占用（如 runner 由 compose 管理）。
            # 显式提示并跳过该模块，而不是报错退出整个脚本。
            Write-Host "[skip] port $Port 由 Docker compose 容器占用（$($proc.ProcessName), PID $procId）。"
            Write-Host "       若该模块由 compose 管理，本机无需再启动；如需本机进程，请先 'docker compose stop' 对应服务。"
            return $false
        }
        else {
            Write-Output "[skip] port $Port -> PID $procId ($($proc.ProcessName)) is NOT owned by $RepoRoot. Pass -Force to kill it anyway."
            exit 1
        }
    }
    return $true
}

function Wait-Healthy {
    param([string]$Module)
    $url = $healthChecks[$Module]
    if (-not $url) { return $true }
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
                Write-Host "[ok] $Module healthy -> $url ($($resp.StatusCode))"
                return $true
            }
        } catch {
            # Not healthy yet (connection refused, 404, 5xx, timeout) — keep polling.
        }
        Start-Sleep -Seconds 1
    }
    Write-Output "[fail] $Module did not become healthy within 60s: $url"
    return $false
}

function Rotate-LogFile {
    param([string]$Path, [long]$MaxBytes = 100MB, [int]$Keep = 5)
    # -live.log / -live-err.log 由 Start-Process 重定向生成，无限增长。
    # 启动前检查大小：超阈值则归档为 <name>.log.<时间戳>，仅保留最近 $Keep 个归档。
    if (-not (Test-Path $Path)) { return }
    $size = (Get-Item $Path).Length
    if ($size -lt $MaxBytes) { return }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $archive = "$Path.$stamp"
    Move-Item -Path $Path -Destination $archive -Force
    Write-Host "[rotate] $Path ($size bytes) -> $(Split-Path $archive -Leaf)"
    $leaf = Split-Path $Path -Leaf
    Get-ChildItem -Path (Split-Path $Path) -Filter "$leaf.*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $Keep |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

function Start-Module {
    param([string]$Module)
    # 每个模块的 stdout/stderr 重定向到其所在目录下的 <module>-live.log / -err.log，
    # 否则 Start-Process 最小化窗口里的启动失败日志会丢失，排障只能靠猜。
    $logDirs = @{
        java   = 'java-backend'
        python = 'python-ai'
        runner = 'docker\plugin-runner'
    }
    $logDir = Join-Path $RepoRoot $logDirs[$Module]
    $outFile = Join-Path $logDir "$Module-live.log"
    $errFile = Join-Path $logDir "$Module-live-err.log"
    Rotate-LogFile -Path $outFile
    Rotate-LogFile -Path $errFile
    switch ($Module) {
        'java' {
            Write-Host "[start] Java backend (mvn spring-boot:run, port 8080)"
            Start-Process -FilePath 'mvn' -ArgumentList 'spring-boot:run' `
                -WorkingDirectory (Join-Path $RepoRoot 'java-backend') -WindowStyle Minimized `
                -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        }
        'python' {
            Write-Host "[start] Python AI (.venv python -m app.main, port 9000)"
            $pyVenv = Join-Path $RepoRoot 'python-ai\.venv\Scripts\python.exe'
            if (-not (Test-Path $pyVenv)) {
                Write-Output "[fail] $Module venv interpreter missing: $pyVenv"
                exit 1
            }
            # 平台内建插件 wheel 目录（P2-3 bid_docx/bid_quote）。docker\.env
            # 已显式设置时以其为准，否则默认指向 provision 脚本的构建产物目录。
            if (-not [Environment]::GetEnvironmentVariable('PLUGIN_BUILTIN_WHEELS_DIR', 'Process')) {
                [Environment]::SetEnvironmentVariable(
                    'PLUGIN_BUILTIN_WHEELS_DIR', (Join-Path $RepoRoot 'python-ai\plugins\dist'), 'Process')
            }
            # 插件签名信任策略目录（与 scripts/plugin-provision.sh 的注册落点一致）。
            if (-not [Environment]::GetEnvironmentVariable('HFUSIONHUB_PLUGIN_TRUST_DIR', 'Process')) {
                [Environment]::SetEnvironmentVariable(
                    'HFUSIONHUB_PLUGIN_TRUST_DIR', (Join-Path $RepoRoot 'python-ai\plugins\trust'), 'Process')
            }
            Start-Process -FilePath $pyVenv -ArgumentList '-m', 'app.main' `
                -WorkingDirectory (Join-Path $RepoRoot 'python-ai') -WindowStyle Minimized `
                -RedirectStandardOutput $outFile -RedirectStandardError $errFile
            # arq 任务队列 worker —— 文档解析为异步任务,没有 worker 消费
            # 会导致上传的文档永远停在"排队中"。与 API 同 venv/Redis。
            $arqOut = Join-Path $logDir 'arq-live.log'
            $arqErr = Join-Path $logDir 'arq-live-err.log'
            Rotate-LogFile -Path $arqOut
            Rotate-LogFile -Path $arqErr
            Write-Host "[start] arq worker (app.core.tasks.arq_tasks.WorkerSettings, redis db2)"
            Start-Process -FilePath $pyVenv -ArgumentList '-m', 'arq', 'app.core.tasks.arq_tasks.WorkerSettings' `
                -WorkingDirectory (Join-Path $RepoRoot 'python-ai') -WindowStyle Minimized `
                -RedirectStandardOutput $arqOut -RedirectStandardError $arqErr
        }
        'runner' {
            Write-Host "[start] Plugin Runner (uvicorn app:app, port 9100)"
            # The runner is installed into the shared python-ai venv (which has
            # uvicorn, fastapi, docker SDK, etc.). There is intentionally no
            # dedicated docker\plugin-runner\.venv. Launch with this interpreter.
            $py = Join-Path $RepoRoot 'python-ai\.venv\Scripts\python.exe'
            if (-not (Test-Path $py)) {
                Write-Output "[fail] $Module venv interpreter missing: $py"
                exit 1
            }
            Start-Process -FilePath $py -ArgumentList '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', '9100' `
                -WorkingDirectory (Join-Path $RepoRoot 'docker\plugin-runner') -WindowStyle Minimized `
                -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        }
        default {
            Write-Warning "Unknown module '$Module' — ignored."
        }
    }
}

Load-EnvFile

# 端口被 Docker compose 容器占用的模块会被标记跳过：不 kill、不启动、不健康检查。
$skipModules = @()
foreach ($m in $Modules) {
    if ($modulePorts.ContainsKey($m)) {
        if (-not (Stop-PortProcess -Port $modulePorts[$m])) {
            $skipModules += $m
        }
    }
}

if ($NoStart) {
    Write-Host 'NoStart set — processes killed, not restarted.'
    exit 0
}

$activeModules = @($Modules | Where-Object { $_ -notin $skipModules })
if ($skipModules.Count -gt 0) {
    Write-Host "跳过被外部占用端口的模块: $($skipModules -join ', ')"
}

$allHealthy = $true
foreach ($m in $activeModules) {
    if ($modulePorts.ContainsKey($m)) {
        Start-Module -Module $m
    }
}

foreach ($m in $activeModules) {
    if (-not $healthChecks.ContainsKey($m)) { continue }
    if (-not (Wait-Healthy -Module $m)) {
        $allHealthy = $false
    }
}

if ($allHealthy) {
    Write-Host 'All requested modules restarted and healthy.'
} else {
    Write-Output 'One or more modules failed to become healthy.'
    exit 1
}
