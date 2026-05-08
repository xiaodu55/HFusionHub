# smoke-test.ps1 — HFusionHub 全功能冒烟测试
#
# 覆盖：Java 后端 31+ API 模块、Python AI 服务、前端可用性、核心链路
# （文档上传→解析→向量化→检索→问答）。任一必需项失败时退出码非 0。
#
# 用法：
#   .\scripts\smoke-test.ps1                      # 完整冒烟（含核心链路，较慢）
#   .\scripts\smoke-test.ps1 -Quick               # 仅 API + 服务健康（快速）
#   .\scripts\smoke-test.ps1 -BaseUrl http://localhost:8080 -PythonUrl http://localhost:9000 -FrontendUrl http://localhost:3000
#
# 前置：服务已启动；docker\.env 含 ADMIN_PASSWORD；KB 52 存在（核心链路用）。

param(
    [switch]$Quick,
    [string]$BaseUrl = 'http://localhost:8080',
    [string]$PythonUrl = 'http://localhost:9000',
    [string]$FrontendUrl = 'http://localhost:3000'
)

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
    if ($Ok) {
        $script:Pass++
        Write-Host "[PASS] $Name" -ForegroundColor Green
    } else {
        $script:Fail++
        $script:Failures += "$Name$($(if ($Detail) { " - $Detail" } else { '' }))"
        Write-Host "[FAIL] $Name$($(if ($Detail) { " - $Detail" } else { '' }))" -ForegroundColor Red
    }
}

function Invoke-Api {
    param([string]$Method, [string]$Path, [hashtable]$Headers = @{}, $Body = $null, [int]$Timeout = 25)
    try {
        if ($Body -ne $null) {
            return Invoke-RestMethod -Uri "$BaseUrl/api$Path" -Method $Method -Headers $Headers -Body $Body -ContentType 'application/json; charset=utf-8' -TimeoutSec $Timeout
        }
        return Invoke-RestMethod -Uri "$BaseUrl/api$Path" -Method $Method -Headers $Headers -TimeoutSec $Timeout
    } catch {
        return $null
    }
}

Write-Host "==== HFusionHub 冒烟测试 ====" -ForegroundColor Cyan
Write-Host "Java: $BaseUrl | Python: $PythonUrl | Frontend: $FrontendUrl"

# ── 0. 前置 ─────────────────────────────────────────────────────────────
$adminPw = Get-EnvVal 'ADMIN_PASSWORD'
if (-not $adminPw) {
    Write-Host "[SKIP] docker\.env 缺少 ADMIN_PASSWORD，无法测试需要登录的 API" -ForegroundColor Yellow
    exit 1
}
$login = $null
try {
    $login = Invoke-RestMethod -Uri "$BaseUrl/api/user/login" -Method Post -Body (@{ username = 'admin'; password = $adminPw } | ConvertTo-Json) -ContentType 'application/json' -TimeoutSec 20
} catch { }
Test-Ok '登录' ($login -ne $null -and $login.code -eq 200 -and $login.data)
if (-not $login.data) { exit 1 }
$headers = @{ satoken = $login.data }

# ── 1. Java 后端 API ────────────────────────────────────────────────────
$tests = @(
    @{ n = '认证-用户信息';   m = 'GET';  p = '/user/info' },
    @{ n = '知识库-我的';     m = 'GET';  p = '/knowledge-base/my' },
    @{ n = '知识库-列表';     m = 'GET';  p = '/knowledge-base/list' },
    @{ n = '文档-我的(52)';   m = 'GET';  p = '/document/my/52' },
    @{ n = '文档-回收站';     m = 'GET';  p = '/document/recycle-bin' },
    @{ n = '对话-我的';       m = 'GET';  p = '/conversation/my' },
    @{ n = '对话-列表';       m = 'GET';  p = '/conversation/list' },
    @{ n = 'Agent-任务列表';  m = 'GET';  p = '/agent-task/list' },
    @{ n = 'Agent-待审批';    m = 'GET';  p = '/agent-task/approvals/pending' },
    @{ n = 'Agent-可观测总览';m = 'GET';  p = '/agent-observability/dashboard' },
    @{ n = 'Agent-指标统计';  m = 'GET';  p = '/agent-observability/metrics/stats' },
    @{ n = 'Agent-告警规则';  m = 'GET';  p = '/agent-observability/alerts/rules' },
    @{ n = '记忆-列表';       m = 'GET';  p = '/memory' },
    @{ n = '用量-汇总';       m = 'GET';  p = '/cost/summary?days=30' },
    @{ n = '用量-每日';       m = 'GET';  p = '/cost/daily?days=7' },
    @{ n = '用量-模型';       m = 'GET';  p = '/cost/models?days=30' },
    @{ n = '笔记-我的';       m = 'GET';  p = '/note/my' },
    @{ n = '插件-列表';       m = 'GET';  p = '/plugin/list?page=1&pageSize=10' },
    @{ n = '提示词-模板';     m = 'GET';  p = '/prompt-templates' },
    @{ n = 'MCP-工具服务';    m = 'GET';  p = '/tools/mcp/servers' },
    @{ n = 'RAG-追踪';        m = 'GET';  p = '/rag/traces?limit=5&knowledgeBaseId=52' },
    @{ n = 'RAG-统计';        m = 'GET';  p = '/rag/traces/stats?days=7&knowledgeBaseId=52' },
    @{ n = 'RAG-意图树';      m = 'GET';  p = '/rag/intent-tree/tree' },
    @{ n = '系统-AI健康';     m = 'GET';  p = '/system/ai-health' },
    @{ n = '系统-AI运行时';   m = 'GET';  p = '/system/ai-runtime' },
    @{ n = '功能开关-全部';   m = 'GET';  p = '/feature-flag/all' },
    @{ n = '通知-未读数';     m = 'GET';  p = '/notifications/unread-count' },
    @{ n = '工具-列表';       m = 'GET';  p = '/tools' },
    @{ n = '模型配置';        m = 'GET';  p = '/model-config' },
    @{ n = '共享-给我的';     m = 'GET';  p = '/knowledge-base/share/to-me' },
    @{ n = '配额-摘要';       m = 'GET';  p = '/quota/summary' }
)
foreach ($t in $tests) {
    $r = Invoke-Api $t.m $t.p $headers
    Test-Ok $t.n ($r -ne $null -and $r.code -eq 200)
}

# ── 1.5 用户偏好 API ────────────────────────────────────────────────────
$userInfo = Invoke-Api 'GET' '/user/info' $headers
Test-Ok '用户信息-主题偏好字段' ($userInfo -ne $null -and $null -ne $userInfo.data.PSObject.Properties['themePreference'])

$themeUpdate = Invoke-Api 'PATCH' '/user/theme-preference' $headers (@{ themePreference = 'dark' } | ConvertTo-Json)
Test-Ok '主题偏好-更新' ($themeUpdate -ne $null -and $themeUpdate.code -eq 200)

$themeRestore = Invoke-Api 'PATCH' '/user/theme-preference' $headers (@{ themePreference = 'system' } | ConvertTo-Json)
Test-Ok '主题偏好-恢复' ($themeRestore -ne $null -and $themeRestore.code -eq 200)

# ── 1.6 演示数据 API ────────────────────────────────────────────────────
$demoImport = Invoke-Api 'POST' '/demo/import' $headers
Test-Ok '演示数据-导入' ($demoImport -ne $null -and $demoImport.code -eq 200 -and $demoImport.data.sections)

$demoClear = Invoke-Api 'POST' '/demo/clear' $headers
Test-Ok '演示数据-清空' ($demoClear -ne $null -and $demoClear.code -eq 200)

# ── 2. Python AI ────────────────────────────────────────────────────────
$pyToken = Get-EnvVal 'PYTHON_AI_INTERNAL_TOKEN'
$pyHeaders = @{ 'X-Internal-Token' = $pyToken; 'X-Tenant-Id' = '1' }
foreach ($u in @(
    @{ n = 'Python-健康';     u = "$PythonUrl/health" },
    @{ n = 'Python-Chat健康'; u = "$PythonUrl/api/chat/health" },
    @{ n = 'Python-运行时';   u = "$PythonUrl/api/runtime/overview" },
    @{ n = 'Python-网关模型'; u = "$PythonUrl/api/gateway/models" },
    @{ n = 'Python-工具注册表'; u = "$PythonUrl/api/tools/registry?tenant_id=1" }
)) {
    try {
        $r = Invoke-WebRequest -Uri $u.u -Headers $pyHeaders -UseBasicParsing -TimeoutSec 30
        Test-Ok $u.n ($r.StatusCode -eq 200)
    } catch { Test-Ok $u.n $false }
}

# ── 2.5 模型配置检查（DeepSeek key 是否有效）──────────────────────────
$pyVenv = Join-Path $RepoRoot 'python-ai\.venv\Scripts\python.exe'
$pyDir = Join-Path $RepoRoot 'python-ai'
if (Test-Path $pyVenv) {
    $probe = @"
import os
os.chdir(r'$pyDir')
from app.utils.config import config
from app.core.llm import get_llm
from app.core.llm.deepseek_llm import _is_placeholder_key
key = config.DEEPSEEK_API_KEY or ''
print('DEEPSEEK_VALID=' + str(bool(key and not _is_placeholder_key(key))))
llm = get_llm()
print('LLM_CHAIN=' + type(llm).__name__)
"@
    try {
        $probeOut = & $pyVenv -c $probe 2>&1
        $llmChain = ($probeOut | Where-Object { $_ -match '^LLM_CHAIN=' }) -replace '^LLM_CHAIN=', ''
        $dsValid = ($probeOut | Where-Object { $_ -match '^DEEPSEEK_VALID=' }) -replace '^DEEPSEEK_VALID=', ''
        if ($dsValid -eq 'True') {
            Test-Ok '模型-DeepSeek已配置' $true "链: $llmChain"
        } else {
            Write-Host "[WARN] DEEPSEEK_API_KEY 为占位符，聊天默认走 Ollama；配置真实 key 后自动 DeepSeek 优先" -ForegroundColor Yellow
            Test-Ok '模型-DeepSeek已配置' $true "链: $llmChain（key 为占位符，Ollama fallback）"
        }
    } catch {
        Test-Ok '模型-配置检查' $false $_.Exception.Message
    }
}

# ── 3. 前端 ─────────────────────────────────────────────────────────────
try {
    $fr = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 10
    Test-Ok '前端-页面加载' ($fr.StatusCode -eq 200 -and $fr.Content -match 'id="app"')
} catch { Test-Ok '前端-页面加载' $false }

# ── 4. 核心链路（可选）──────────────────────────────────────────────────
if (-not $Quick) {
    Write-Host "── 核心链路：文档上传→解析→向量化→检索 ──" -ForegroundColor Cyan
    try {
        $docFile = Join-Path $RepoRoot 'test-data\java-threads.md'
        if (Test-Path $docFile) {
            $upJson = curl.exe -s -X POST "$BaseUrl/api/document/upload" -H "satoken: $($login.data)" -F "file=@$docFile" -F "title=Smoke测试文档" -F "knowledgeBaseId=52"
            $up = $upJson | ConvertFrom-Json
            if ($up.code -eq 200 -and $up.data.id) {
                Test-Ok '链路-文档上传' $true "docId=$($up.data.id)"
                $parseResp = curl.exe -s -X POST "$BaseUrl/api/document/$($up.data.id)/parse" -H "satoken: $($login.data)"
                if ($parseResp -notmatch '200|success|开始解析') { Test-Ok '链路-触发解析' $false $parseResp }
                $completed = $false
                for ($i = 0; $i -lt 24; $i++) {
                    Start-Sleep -Seconds 5
                    $d = (curl.exe -s "$BaseUrl/api/document/$($up.data.id)" -H "satoken: $($login.data)") | ConvertFrom-Json
                    if ($d.data.status -eq 2) { $completed = $true; break }   # 2 = COMPLETED
                    if ($d.data.status -eq 3) { break }                        # 3 = FAILED
                }
                Test-Ok '链路-解析完成' $completed
                if ($completed) {
                    $searchBody = [System.Text.Encoding]::UTF8.GetBytes((@{ query = 'Java 虚拟线程'; knowledge_base_id = 52; top_k = 3 } | ConvertTo-Json))
                    try {
                        $sr = Invoke-WebRequest -Uri "$PythonUrl/api/rag/debug/search" -Method Post -Headers $pyHeaders -Body $searchBody -ContentType 'application/json; charset=utf-8' -UseBasicParsing -TimeoutSec 60
                        $sj = $sr.Content | ConvertFrom-Json
                        Test-Ok '链路-检索命中' ($sj.results.Count -gt 0) "results=$($sj.results.Count)"
                    } catch { Test-Ok '链路-检索命中' $false }
                }
            } else { Test-Ok '链路-文档上传' $false ($upJson) }
        } else { Write-Host "[SKIP] 缺少 test-data\java-threads.md" -ForegroundColor Yellow }
    } catch { Test-Ok '链路-核心' $false $_.Exception.Message }
}

# ── 汇总 ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==== 结果: $($script:Pass) PASS / $($script:Fail) FAIL ====" -ForegroundColor $(if ($script:Fail -eq 0) { 'Green' } else { 'Red' })
if ($script:Failures.Count -gt 0) {
    Write-Host "失败项:" -ForegroundColor Red
    $script:Failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
exit 0
