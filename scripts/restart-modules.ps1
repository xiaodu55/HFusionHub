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

$RepoRoot = Split-Path -Parent $PSScriptRoot
$modulePorts = @{
    java   = 8080
    python = 9000
    runner = 9100
}

$healthChecks = @{
    java   = 'http://localhost:8080/actuator/health'
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

function Stop-PortProcess {
    param([int]$Port)
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
        else {
            Write-Output "[skip] port $Port -> PID $procId ($($proc.ProcessName)) is NOT owned by $RepoRoot. Pass -Force to kill it anyway."
            exit 1
        }
    }
}

function Wait-Healthy {
    param([string]$Module)
    $url = $healthChecks[$Module]
    if (-not $url) { return $true }
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($resp.StatusCode -lt 500) {
                Write-Host "[ok] $Module healthy -> $url ($($resp.StatusCode))"
                return $true
            }
        } catch {
            # Not healthy yet (connection refused, 5xx, timeout) — keep polling.
        }
        Start-Sleep -Seconds 1
    }
    Write-Output "[fail] $Module did not become healthy within 60s: $url"
    return $false
}

function Start-Module {
    param([string]$Module)
    switch ($Module) {
        'java' {
            Write-Host "[start] Java backend (mvn spring-boot:run, port 8080)"
            Start-Process -FilePath 'mvn' -ArgumentList 'spring-boot:run' `
                -WorkingDirectory (Join-Path $RepoRoot 'java-backend') -WindowStyle Minimized
        }
        'python' {
            Write-Host "[start] Python AI (.venv python -m app.main, port 9000)"
            $pyVenv = Join-Path $RepoRoot 'python-ai\.venv\Scripts\python.exe'
            if (-not (Test-Path $pyVenv)) {
                Write-Output "[fail] $Module venv interpreter missing: $pyVenv"
                exit 1
            }
            Start-Process -FilePath $pyVenv -ArgumentList '-m', 'app.main' `
                -WorkingDirectory (Join-Path $RepoRoot 'python-ai') -WindowStyle Minimized
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
                -WorkingDirectory (Join-Path $RepoRoot 'docker\plugin-runner') -WindowStyle Minimized
        }
        default {
            Write-Warning "Unknown module '$Module' — ignored."
        }
    }
}

Load-EnvFile

foreach ($m in $Modules) {
    if ($modulePorts.ContainsKey($m)) {
        Stop-PortProcess -Port $modulePorts[$m]
    }
}

if ($NoStart) {
    Write-Host 'NoStart set — processes killed, not restarted.'
    exit 0
}

$allHealthy = $true
foreach ($m in $Modules) {
    if ($modulePorts.ContainsKey($m)) {
        Start-Module -Module $m
    }
}

foreach ($m in $Modules) {
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
