# get-tunnel-url.ps1 — 查询 cpolar 内网穿透的当前公网 URL
#
# cpolar 免费版隧道重连后会分配新域名，旧地址变为 404。
# 本脚本读取 cpolar 服务日志，识别"前端(3000)"与"API(8080)"的当前地址。
#
# 用法：
#   .\scripts\get-tunnel-url.ps1          # 显示前端 + API 两个公网 URL
#   .\scripts\get-tunnel-url.ps1 -Front   # 仅显示前端 URL
#   .\scripts\get-tunnel-url.ps1 -Api     # 仅显示 API URL

param(
    [switch]$Front,
    [switch]$Api
)

$logDir = Join-Path $env:USERPROFILE '.cpolar\logs'
$logFile = Get-ChildItem $logDir -Filter 'cpolar_service.log.*' -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $logFile) {
    Write-Host "[ERR] 未找到 cpolar 服务日志（$logDir）" -ForegroundColor Red
    exit 1
}

$urls = Select-String -Path $logFile.FullName -Pattern 'https?://[a-zA-Z0-9._-]+\.(?:cpolar\.(?:top|cn)|[a-z0-9]+\.cpolar\.cn)' |
    ForEach-Object { $_.Matches[0].Value } | Select-Object -Unique

$frontUrl = $null
$apiUrl = $null
foreach ($u in $urls) {
    try {
        $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 12
        if ($r.Content -match 'id="app"') { $frontUrl = $u }
        else { $apiUrl = $u }
    } catch { }
}

if ($Front -or (-not $Api -and -not $Front)) {
    if ($frontUrl) { Write-Output "前端: $frontUrl" } else { Write-Host "[WARN] 未识别到前端(3000)隧道，尝试手动验证 http/https 前缀" -ForegroundColor Yellow }
}
if ($Api -or (-not $Api -and -not $Front)) {
    if ($apiUrl) { Write-Output "API : $apiUrl" } else { Write-Host "[WARN] 未识别到 API(8080) 隧道" -ForegroundColor Yellow }
}
if (-not $frontUrl -and -not $apiUrl) {
    Write-Host "[WARN] 无法识别隧道 URL，请确认：cpolar 服务运行中（sc query cpolar）、本机 3000/8080 已启动" -ForegroundColor Yellow
}
