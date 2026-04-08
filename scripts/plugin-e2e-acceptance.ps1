<#!
.SYNOPSIS
  Exercises plugin-runner against the isolated TLS Docker Engine created by
  staging-rehearsal.ps1. It never talks to the host Docker socket from Runner.

.DESCRIPTION
  The script builds a deterministic hfusionhub-plugin-* image on the isolated
  Engine, then reaches Runner through its Compose container. It verifies a
  valid digest, a wrong digest, image allowlist rejection, resource limits,
  and an allow/block network pair against a short-lived in-engine HTTP server.

  Business workflow contracts (approval-token consume and quota reserve/settle)
  remain tenant-scoped Java/Python tests: they require an actual plugin record,
  agent run, and tenant rather than test data invented by this script.
#>
[CmdletBinding()]
param(
    [string]$ImageTag = "hfusionhub-plugin-acceptance:v1",
    [string]$DindHost = "tcp://127.0.0.1:2376",
    [string]$DindCertPath,
    [switch]$KeepImage
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root "deploy\.env"
if (-not $DindCertPath) {
    $DindCertPath = Join-Path $Root "deploy\runner-tls\dind-certs\client"
}
$Fixture = Join-Path $Root "docker\plugin-runner\acceptance-fixture"
$NetworkName = "plugin-isolated"

function Get-EnvFileValue {
    param([string]$Name)
    $line = Select-String -Path $EnvFile -Pattern "^$Name=" | Select-Object -First 1
    if (-not $line) { throw "Missing $Name in $EnvFile" }
    return $line.Line.Substring($Name.Length + 1)
}

function Invoke-DindDocker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $saved = @{
        DOCKER_HOST = $env:DOCKER_HOST
        DOCKER_TLS_VERIFY = $env:DOCKER_TLS_VERIFY
        DOCKER_CERT_PATH = $env:DOCKER_CERT_PATH
        DOCKER_BUILDKIT = $env:DOCKER_BUILDKIT
    }
    try {
        $env:DOCKER_HOST = $DindHost
        $env:DOCKER_TLS_VERIFY = "1"
        $env:DOCKER_CERT_PATH = $DindCertPath
        # Docker Desktop's selected Buildx builder can ignore DOCKER_HOST.
        # The legacy client path deliberately builds against the isolated daemon.
        $env:DOCKER_BUILDKIT = "0"
        $output = & docker @Arguments
        if ($LASTEXITCODE -ne 0) { throw "dind docker command failed: docker $($Arguments -join ' ')" }
        return $output
    } finally {
        foreach ($key in $saved.Keys) {
            if ($null -eq $saved[$key]) { Remove-Item "Env:$key" -ErrorAction SilentlyContinue }
            else { Set-Item "Env:$key" $saved[$key] }
        }
    }
}

function Invoke-Runner {
    param([hashtable]$Body, [string]$RunnerToken)
    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(
        ($Body | ConvertTo-Json -Depth 10 -Compress)
    ))
    $clientCode = @'
import base64, json, os, urllib.error, urllib.request
body = base64.b64decode(os.environ["RUNNER_PAYLOAD"]).decode("utf-8")
request = urllib.request.Request(
    "http://127.0.0.1:9100/execute", data=body.encode("utf-8"),
    headers={"Content-Type": "application/json", "X-Runner-Token": os.environ["RUNNER_TOKEN"]},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=40) as response:
        print(json.dumps({"status": response.status, "body": json.loads(response.read())}))
except urllib.error.HTTPError as error:
    print(json.dumps({"status": error.code, "body": json.loads(error.read())}))
'@
    # Feed code through stdin instead of `python -c`: Docker Desktop's Windows
    # argument parsing strips nested quotes from a Python command string.
    $raw = $clientCode | & docker exec -i -e "RUNNER_TOKEN=$RunnerToken" -e "RUNNER_PAYLOAD=$payload" `
        hfusionhub-plugin-runner python -
    if ($LASTEXITCODE -ne 0) { throw "Runner request helper failed" }
    return ($raw | ConvertFrom-Json)
}

function Assert-Status {
    param([object]$Response, [int]$Expected, [string]$Name)
    if ([int]$Response.status -ne $Expected) {
        throw "$Name expected HTTP $Expected, got $($Response.status): $($Response.body | ConvertTo-Json -Compress)"
    }
}

function Ensure-DindNetwork {
    param([string]$Name)
    $existing = Invoke-DindDocker network ls --filter "name=^$Name$" --format '{{.Name}}'
    if (($existing | Where-Object { $_ -eq $Name })) {
        return $false
    } else {
        Invoke-DindDocker network create --driver bridge $Name | Out-Null
        return $true
    }
}

if (-not (Test-Path $EnvFile)) { throw "Run staging-rehearsal.ps1 first: $EnvFile is absent" }
if (-not (Test-Path (Join-Path $DindCertPath "ca.pem"))) { throw "dind client TLS files are absent: $DindCertPath" }
if (-not (Test-Path $Fixture)) { throw "Acceptance fixture is absent: $Fixture" }

$RunnerToken = Get-EnvFileValue "PLUGIN_RUNNER_TOKEN"
$serverName = "hfh-acceptance-http-$([Guid]::NewGuid().ToString('N').Substring(0, 8))"
$serverStarted = $false
$networkCreated = $false

try {
    Write-Host "[1/6] Verifying isolated Docker Engine TLS connection..."
    Invoke-DindDocker version --format '{{.Server.Version}}' | Out-Null
    $networkCreated = Ensure-DindNetwork $NetworkName
    Write-Host "[2/6] Building acceptance plugin in isolated Engine..."
    Invoke-DindDocker build -t $ImageTag $Fixture | Out-Null
    $digest = (Invoke-DindDocker image inspect --format '{{.Id}}' $ImageTag | Select-Object -First 1).Trim()
    if ($digest -notmatch '^sha256:[0-9a-f]{64}$') { throw "Unexpected image digest: $digest" }

    $base = @{ image_tag = $ImageTag; image_digest = $digest }
    function New-ExecutionRequest {
        param([hashtable]$Fields)
        $request = @{}
        foreach ($key in $base.Keys) { $request[$key] = $base[$key] }
        foreach ($key in $Fields.Keys) { $request[$key] = $Fields[$key] }
        return $request
    }

    Write-Host "[3/6] Verifying valid digest execution..."
    $valid = Invoke-Runner -RunnerToken $RunnerToken -Body (New-ExecutionRequest @{
        tool_name = "echo_tool"; tool_input = @{ text = "isolated-engine" }; config = @{ timeout = 15 }
    })
    Assert-Status $valid 200 "valid digest"
    if (-not $valid.body.success -or $valid.body.data.echo -ne "isolated-engine") {
        throw "valid digest did not execute the plugin tool"
    }

    Write-Host "[4/6] Verifying wrong digest and image allowlist rejection..."
    $wrong = Invoke-Runner -RunnerToken $RunnerToken -Body (New-ExecutionRequest @{
        image_digest = "sha256:" + ("0" * 64); tool_name = "echo_tool"; tool_input = @{}
    })
    Assert-Status $wrong 400 "wrong digest"

    $forbidden = Invoke-Runner -RunnerToken $RunnerToken -Body @{
        image_tag = "untrusted-plugin:v1"; image_digest = $digest; tool_name = "echo_tool"; tool_input = @{}
    }
    Assert-Status $forbidden 403 "image allowlist"

    Write-Host "[5/6] Verifying resource limits..."
    $limited = Invoke-Runner -RunnerToken $RunnerToken -Body (New-ExecutionRequest @{
        tool_name = "resource_report_tool"; tool_input = @{}; config = @{
            timeout = 15; memory_limit = "64m"; cpu_limit = 0.5; pids_limit = 128; read_only_rootfs = $true
        }
    })
    Assert-Status $limited 200 "resource limits"
    if ($limited.body.resource_limits.memory_bytes -ne 67108864 -or
        $limited.body.resource_limits.cpu_quota -ne 50000 -or
        $limited.body.resource_limits.pids_limit -ne 128 -or
        -not $limited.body.resource_limits.read_only_rootfs) {
        throw "runner did not report the requested resource limits"
    }

    Write-Host "[6/6] Verifying network allow and block policies..."
    Write-Host "  Starting an in-engine HTTP server..."
    Invoke-DindDocker create --name $serverName --network $NetworkName $ImageTag python -m http.server 8080 | Out-Null
    Invoke-DindDocker start $serverName | Out-Null
    $serverStarted = $true
    Start-Sleep -Seconds 1
    Write-Host "  Resolving the in-engine HTTP server address..."
    $serverIp = (Invoke-DindDocker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $serverName | Select-Object -First 1).Trim()
    if (-not $serverIp) { throw "acceptance HTTP server has no bridge address" }

    Write-Host "  Probing the allowlisted address $serverIp..."
    $allowed = Invoke-Runner -RunnerToken $RunnerToken -Body (New-ExecutionRequest @{
        tool_name = "network_probe_tool"; tool_input = @{ url = "http://${serverIp}:8080" }
        config = @{ timeout = 15; allowed_domains = @($serverIp) }
    })
    Assert-Status $allowed 200 "allowed network"
    if (-not $allowed.body.data.ok) { throw "allowed network probe was blocked" }

    Write-Host "  Probing the blocklisted address $serverIp..."
    $blocked = Invoke-Runner -RunnerToken $RunnerToken -Body (New-ExecutionRequest @{
        tool_name = "network_probe_tool"; tool_input = @{ url = "http://${serverIp}:8080" }
        config = @{ timeout = 15; blocked_domains = @($serverIp) }
    })
    Assert-Status $blocked 200 "blocked network"
    if ($blocked.body.data.ok) { throw "blocked network probe reached the HTTP server" }

    Write-Host "Plugin isolated-engine acceptance passed: digest, allowlist, limits, and network policies."
} finally {
    if ($serverStarted) {
        try { Invoke-DindDocker rm -f $serverName | Out-Null } catch { }
    }
    if (-not $KeepImage) {
        try { Invoke-DindDocker image rm -f $ImageTag | Out-Null } catch { }
    }
    if ($networkCreated) {
        try { Invoke-DindDocker network rm $NetworkName | Out-Null } catch { }
    }
}
