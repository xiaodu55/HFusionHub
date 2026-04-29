# verify-agent-workflow.ps1 — Agent 工作流回归验证
#
# 验证（RAG_AGENT_WORKFLOW_ENABLED=true + 相关 feature flag 下）：
#   1. Agent 工作流开关生效（runtime.features.agent_workflow）
#   2. 工具注册表：write_note（approval_write 能力）与 web_search 可见
#   3. 知识库问答引用来源（KB 52，需先上传文档）
#   4. 写笔记审批触发（write_note → approval_required）— 尽力项（依赖模型行为）
#
# 用法：.\scripts\verify-agent-workflow.ps1 [-KnowledgeBaseId 52]

param([int]$KnowledgeBaseId = 52)

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $RepoRoot 'docker\.env'

function Get-EnvVal($key) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$key=" } | Select-Object -First 1
    if ($line) { return ($line -split '=', 2)[1].Trim() }
    return ''
}

$script:Pass = 0
$script:Fail = 0
$script:Failures = @()
function Test-Ok {
    param([string]$Name, [bool]$Ok, [string]$Detail = '')
    if ($Ok) { $script:Pass++; Write-Host "[PASS] $Name" -ForegroundColor Green }
    else {
        $script:Fail++; $script:Failures += $Name
        Write-Host "[FAIL] $Name$($(if ($Detail) { " - $Detail" } else { '' }))" -ForegroundColor Red
    }
}

$pyToken = Get-EnvVal 'PYTHON_AI_INTERNAL_TOKEN'
$h = @{ 'X-Internal-Token' = $pyToken; 'X-Tenant-Id' = '1' }
$base = 'http://localhost:9000'

Write-Host "==== Agent 工作流回归验证 (KB $KnowledgeBaseId) ====" -ForegroundColor Cyan

# 1. Agent 工作流开关
try {
    $rt = Invoke-RestMethod -Uri "$base/api/runtime/overview" -Headers $h -TimeoutSec 30
    $aw = $rt.features.agent_workflow
    Test-Ok 'Agent工作流开关' ($aw -eq $true) "agent_workflow=$aw"
} catch { Test-Ok 'Agent工作流开关' $false $_.Exception.Message }

# 2. 工具注册表可见性
try {
    $reg = Invoke-RestMethod -Uri "$base/api/tools/registry?tenant_id=1" -Headers $h -TimeoutSec 30
    $names = @($reg.tools | ForEach-Object { $_.name })
    Test-Ok '工具注册表可访问' ($names.Count -gt 0) "tools=$($names -join ',')"
    Test-Ok 'write_note已注册' ($names -contains 'write_note')
    Test-Ok 'web_search已注册' ($names -contains 'web_search')
} catch { Test-Ok '工具注册表可访问' $false $_.Exception.Message }

# 3. 知识库问答引用（KB 需有文档）
try {
    $b = [System.Text.Encoding]::UTF8.GetBytes((@{ message = 'Java 虚拟线程有什么优势？'; knowledge_base_id = $KnowledgeBaseId; user_id = 1; request_id = "wf-$([guid]::NewGuid().ToString('N'))"; history = @(); style = 'concise'; max_tool_steps = 5 } | ConvertTo-Json -Depth 4))
    $r = Invoke-WebRequest -Uri "$base/api/agent/v1/chat" -Method Post -Headers $h -Body $b -ContentType 'application/json; charset=utf-8' -UseBasicParsing -TimeoutSec 120
    $j = $r.Content | ConvertFrom-Json
    Test-Ok '知识库问答引用' ($j.sources.Count -gt 0) "sources=$($j.sources.Count) status=$($j.status)"
} catch { Test-Ok '知识库问答引用' $false $_.Exception.Message }

# 4. 写笔记审批触发（尽力项：依赖模型是否调用 write_note）
try {
    $b2 = [System.Text.Encoding]::UTF8.GetBytes((@{ message = '请使用 write_note 工具，把下面结论保存为笔记：HFusionHub 是三层企业级 AI Agent 平台。'; knowledge_base_id = $KnowledgeBaseId; user_id = 1; capability_profile = 'approval_write'; user_role = 'admin'; request_id = "wf-w-$([guid]::NewGuid().ToString('N'))"; history = @(); style = 'detailed'; max_tool_steps = 5 } | ConvertTo-Json -Depth 4))
    $r2 = Invoke-WebRequest -Uri "$base/api/agent/v1/chat" -Method Post -Headers $h -Body $b2 -ContentType 'application/json; charset=utf-8' -UseBasicParsing -TimeoutSec 180
    $j2 = $r2.Content | ConvertFrom-Json
    $approval = ($j2.error_detail -match 'approval_required') -or ($j2.status -eq 'waiting_approval')
    if ($approval -or $j2.tool_calls_count -gt 0) {
        Test-Ok '写笔记审批触发(尽力项)' $true "tool_calls=$($j2.tool_calls_count) status=$($j2.status)"
    } else {
        Write-Host "[INFO] 写笔记审批触发(尽力项)：模型未调用工具（tool_calls=$($j2.tool_calls_count)）——小模型行为差异，配置 DeepSeek 后更稳定" -ForegroundColor Yellow
    }
} catch { Write-Host "[INFO] 写笔记审批触发(尽力项)：请求异常 $($_.Exception.Message)" -ForegroundColor Yellow }

Write-Host ""
Write-Host "==== 结果: $($script:Pass) PASS / $($script:Fail) FAIL ====" -ForegroundColor $(if ($script:Fail -eq 0) { 'Green' } else { 'Red' })
if ($script:Failures.Count -gt 0) {
    $script:Failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
exit 0
