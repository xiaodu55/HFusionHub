$body = Get-Content "D:\college\development\HFusionHub1\python-ai\verify-body.json" -Raw
$token = "***REMOVED-BY-REWRITE***"
$client = [System.Net.Http.HttpClient]::new()
$req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, "http://127.0.0.1:9000/api/agent/v1/chat/stream")
[void]$req.Headers.TryAddWithoutValidation("X-Internal-Token", $token)
[void]$req.Headers.TryAddWithoutValidation("X-Tenant-Id", "1")
$req.Content = [System.Net.Http.StringContent]::new($body, [System.Text.Encoding]::UTF8, "application/json")
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$resp = $client.SendAsync($req, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
Write-Host "status: $($resp.StatusCode) headers after $([Math]::Round($sw.Elapsed.TotalSeconds,1))s"
$stream = $resp.Content.ReadAsStreamAsync().Result
$reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8)
$firstToken = $null
$chunkCount = 0
while (-not $reader.EndOfStream) {
    $line = $reader.ReadLine()
    if ($line -match '"content"' -and $null -eq $firstToken) {
        $firstToken = $sw.Elapsed.TotalSeconds
        Write-Host "FIRST content token at $([Math]::Round($firstToken,1))s"
    }
    if ($line -match '"content"') { $chunkCount++ }
    if ($line -match '\[DONE\]') { Write-Host "DONE at $([Math]::Round($sw.Elapsed.TotalSeconds,1))s" }
}
Write-Host "total content chunks: $chunkCount, total time: $([Math]::Round($sw.Elapsed.TotalSeconds,1))s"
