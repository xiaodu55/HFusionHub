<#
.SYNOPSIS
  E2E acceptance for the P2-3 platform built-in plugins (bid_docx / bid_quote)
  against a live plugin-runner + isolated dind engine.

.DESCRIPTION
  Verifies the full container-sandbox execution path that production uses:
    1. Both built-in plugin images exist in the isolated engine (loaded by
       scripts/plugin-provision.sh).
    2. bid_export_docx renders a real .docx (ZIP magic) via /execute with a
       valid image digest.
    3. bid_export_quote renders a real .xlsx and the embedded scoring/quote
       math matches expectations (reuses bid_calc_scoring semantics).
    4. Fail-closed supply chain: a wrong digest and a missing digest are both
       rejected by the runner before any container is started.

  Requests are issued from INSIDE the runner container (docker exec python),
  so the script works whether or not :9100 is published to the host, and
  mirrors scripts/plugin-e2e-acceptance.ps1.

.PREREQUISITES
  - staging-rehearsal (dind + plugin-runner) or dev compose dind sidecar is up
  - scripts/plugin-provision.sh has been run (images loaded into the engine)

.USAGE
  .\scripts\plugin-builtins-e2e.ps1
  .\scripts\plugin-builtins-e2e.ps1 -RunnerContainer plugin-runner
#>
[CmdletBinding()]
param(
    [string]$RunnerContainer = "hfusionhub-plugin-runner",
    [string]$EnvFile,
    [string]$DindHost = "tcp://127.0.0.1:2376",
    [string]$DindCertPath,
    [string]$DocxImage = "hfusionhub-plugin-bid-docx:1.0.0",
    [string]$QuoteImage = "hfusionhub-plugin-bid-quote:1.0.0",
    [string]$NetworkName = "plugin-isolated"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot "docker\.env" }
if (-not $DindCertPath) { $DindCertPath = Join-Path $RepoRoot "deploy\runner-tls\dind-certs\client" }

function Get-EnvFileValue {
    param([string]$Path, [string]$Name)
    $line = Select-String -Path $Path -Pattern "^$Name=" | Select-Object -First 1
    if (-not $line) { throw "Missing $Name in $Path" }
    return $line.Line.Substring($Name.Length + 1)
}

function Invoke-DindDocker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $saved = @{
        DOCKER_HOST       = $env:DOCKER_HOST
        DOCKER_TLS_VERIFY = $env:DOCKER_TLS_VERIFY
        DOCKER_CERT_PATH  = $env:DOCKER_CERT_PATH
        DOCKER_BUILDKIT   = $env:DOCKER_BUILDKIT
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
    with urllib.request.urlopen(request, timeout=90) as response:
        print(json.dumps({"status": response.status, "body": json.loads(response.read())}))
except urllib.error.HTTPError as error:
    print(json.dumps({"status": error.code, "body": json.loads(error.read())}))
'@
    # Feed code through stdin instead of `python -c`: Docker Desktop's Windows
    # argument parsing strips nested quotes from a Python command string.
    $raw = $clientCode | & docker exec -i -e "RUNNER_TOKEN=$RunnerToken" -e "RUNNER_PAYLOAD=$payload" `
        $RunnerContainer python -
    if ($LASTEXITCODE -ne 0) { throw "Runner request helper failed" }
    return ($raw | ConvertFrom-Json)
}

$script:Pass = 0
$script:Fail = 0
function Assert {
    param([bool]$Condition, [string]$Label)
    if ($Condition) {
        $script:Pass++
        Write-Host "  PASS  $Label" -ForegroundColor Green
    } else {
        $script:Fail++
        Write-Host "  FAIL  $Label" -ForegroundColor Red
    }
}

function Assert-Status {
    param([object]$Response, [int]$Expected, [string]$Name)
    if ([int]$Response.status -ne $Expected) {
        throw "$Name expected HTTP $Expected, got $($Response.status): $($Response.body | ConvertTo-Json -Compress)"
    }
}

function Assert-ZipPayload {
    param([object]$Data, [string]$Label)
    $bytes = [Convert]::FromBase64String($Data.base64)
    Assert ($bytes.Length -gt 1000) "$Label payload is a non-trivial byte stream ($($bytes.Length) bytes)"
    Assert (($bytes[0] -eq 0x50) -and ($bytes[1] -eq 0x4B)) "$Label payload starts with ZIP magic (docx/xlsx container)"
}

# ── 前置检查 ──────────────────────────────────────────────────────────────
if (-not (Test-Path $EnvFile)) { throw "docker\.env is absent: $EnvFile" }
if (-not (Test-Path (Join-Path $DindCertPath "ca.pem"))) { throw "dind client TLS files are absent: $DindCertPath" }

$RunnerToken = Get-EnvFileValue -Path $EnvFile -Name "PLUGIN_RUNNER_TOKEN"

Write-Host "[1/5] Verifying isolated Docker Engine and built-in images..."
Invoke-DindDocker version --format '{{.Server.Version}}' | Out-Null
$existingNetworks = @(Invoke-DindDocker network ls --filter "name=^$NetworkName$" --format '{{.Name}}')
if (-not ($existingNetworks | Where-Object { $_ -eq $NetworkName })) {
    Invoke-DindDocker network create --driver bridge $NetworkName | Out-Null
}
foreach ($image in @($DocxImage, $QuoteImage)) {
    $null = Invoke-DindDocker image inspect $image
}
$docxDigest = (Invoke-DindDocker image inspect --format '{{.Id}}' $DocxImage | Select-Object -First 1).Trim()
$quoteDigest = (Invoke-DindDocker image inspect --format '{{.Id}}' $QuoteImage | Select-Object -First 1).Trim()
if ($docxDigest -notmatch '^sha256:[0-9a-f]{64}$') { throw "Unexpected bid_docx digest: $docxDigest" }
if ($quoteDigest -notmatch '^sha256:[0-9a-f]{64}$') { throw "Unexpected bid_quote digest: $quoteDigest" }

Write-Host "[2/5] Executing bid_docx::bid_export_docx in sandbox..."
$docx = Invoke-Runner -RunnerToken $RunnerToken -Body @{
    image_tag    = $DocxImage
    image_digest = $docxDigest
    plugin_id    = "bid_docx@1.0.0"
    tool_name    = "bid_export_docx"
    tool_input   = @{
        title  = "E2E Bid Document"
        meta   = @{
            tender_number = "T-E2E-2026-001"
            project_title = "Plugin E2E Project"
            bidder_name   = "HFusionHub E2E Bidder"
            deadline      = "2026-09-30"
            budget        = "USD 1,000,000"
        }
        sections = @(
            @{ key = "tech";  title = "Technical Approach"; content = "Layered architecture.`n`n# Highlights`nSandboxed container execution with digest pinning." },
            @{ key = "price"; title = "Pricing Summary";    content = "See the bid_quote xlsx export." }
        )
    }
    config       = @{ timeout = 60 }
}
Assert-Status -Response $docx -Expected 200 -Name "bid_docx execute"
Assert ($docx.body.success -eq $true) "bid_docx execution succeeded"
Assert ($docx.body.data.filename -like "*.docx") "bid_docx filename ends with .docx ($($docx.body.data.filename))"
Assert ([int]$docx.body.data.chars -gt 0) "bid_docx char count reported ($($docx.body.data.chars))"
Assert-ZipPayload -Data $docx.body.data -Label "bid_docx"

Write-Host "[3/5] Executing bid_quote::bid_export_quote in sandbox (quote math + scoring)..."
$quote = Invoke-Runner -RunnerToken $RunnerToken -Body @{
    image_tag    = $QuoteImage
    image_digest = $quoteDigest
    plugin_id    = "bid_quote@1.0.0"
    tool_name    = "bid_export_quote"
    tool_input   = @{
        meta  = @{
            tender_number = "T-E2E-2026-001"
            project_title = "Plugin E2E Project"
            bidder_name   = "HFusionHub E2E Bidder"
            currency      = "CNY"
        }
        items  = @(
            @{ name = "App Server"; spec = "8C16G"; unit = "unit";  qty = 2; unit_price = 3000; tax_rate = 0.06 },
            @{ name = "Integration"; spec = "";     unit = "pers"; qty = 1; unit_price = 4000; tax_rate = 0.06 }
        )
        points = @(
            @{ name = "technical"; max_score = 60; weight = 0.6 },
            @{ name = "commercial"; max_score = 40; weight = 0.4 }
        )
        scores = @(
            @{ name = "technical"; score = 54 },
            @{ name = "commercial"; score = 31 }
        )
    }
    config       = @{ timeout = 60 }
}
Assert-Status -Response $quote -Expected 200 -Name "bid_quote execute"
Assert ($quote.body.success -eq $true) "bid_quote execution succeeded"
Assert ($quote.body.data.filename -like "*.xlsx") "bid_quote filename ends with .xlsx ($($quote.body.data.filename))"
Assert ([double]$quote.body.data.totals.subtotal -eq 10000) "bid_quote subtotal == 10000 (got $($quote.body.data.totals.subtotal))"
Assert ([double]$quote.body.data.totals.tax_amount -eq 600) "bid_quote tax == 600 (got $($quote.body.data.totals.tax_amount))"
Assert ([double]$quote.body.data.totals.grand_total -eq 10600) "bid_quote grand total == 10600 (got $($quote.body.data.totals.grand_total))"
Assert ([int]$quote.body.data.lines -eq 2) "bid_quote line count == 2"
Assert ([double]$quote.body.data.scoring.total_score -eq 85) "bid_quote scoring total == 85 (got $($quote.body.data.scoring.total_score))"
Assert ([double]$quote.body.data.scoring.weighted_total -eq 44.8) "bid_quote weighted total == 44.8 (got $($quote.body.data.scoring.weighted_total))"
Assert-ZipPayload -Data $quote.body.data -Label "bid_quote"

Write-Host "[4/5] Verifying fail-closed: wrong image digest is rejected..."
$wrong = Invoke-Runner -RunnerToken $RunnerToken -Body @{
    image_tag    = $DocxImage
    image_digest = "sha256:" + ("0" * 64)
    tool_name    = "bid_export_docx"
    tool_input   = @{ sections = @(@{ key = "k"; title = "t"; content = "c" }) }
}
Assert-Status -Response $wrong -Expected 400 -Name "wrong digest"
Assert ($wrong.body.detail -like "*digest mismatch*") "wrong digest rejected with mismatch detail"

Write-Host "[5/5] Verifying fail-closed: missing image digest is rejected..."
$missing = Invoke-Runner -RunnerToken $RunnerToken -Body @{
    image_tag  = $DocxImage
    tool_name  = "bid_export_docx"
    tool_input = @{ sections = @(@{ key = "k"; title = "t"; content = "c" }) }
}
Assert-Status -Response $missing -Expected 400 -Name "missing digest"
Assert ($missing.body.detail -like "*digest*required*") "missing digest rejected as required"

Write-Host ""
if ($script:Fail -gt 0) {
    Write-Host "plugin-builtins e2e: $script:Pass passed, $script:Fail FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "plugin-builtins e2e: all $script:Pass checks passed" -ForegroundColor Green
exit 0
