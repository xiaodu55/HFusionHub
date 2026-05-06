# 性能基线测试指南

## 测试目标

建立 HFusionHub 各核心功能的性能基线，用于：
- 版本迭代对比（回归检测）
- 容量规划（资源评估）
- 瓶颈识别（优化方向）

---

## 测试环境要求

### 硬件规格
- CPU：4 核 / 8 线程（最低）
- 内存：16 GB
- 磁盘：SSD（NVMe 推荐）
- 网络：千兆局域网

### 软件版本
- Docker：24.0+
- JDK：21
- Python：3.11
- MySQL：8.0
- Milvus：2.3+

### 初始状态
- 空数据库（仅 admin 用户）
- 缓存已预热（启动后等待 30 秒）
- 无其他负载

---

## 快速冒烟测试（5 分钟）

验证所有服务可用性：

```powershell
.\scripts\smoke-test.ps1
```

**预期结果**：
```
==== 结果: 40+ PASS / 0 FAIL ====
```

---

## 核心链路性能测试

### 1. 文档上传→解析→向量化（端到端）

**测试脚本**：`scripts\benchmark-document-pipeline.ps1`

```powershell
# benchmark-document-pipeline.ps1
param(
    [int]$Iterations = 10,
    [string]$BaseUrl = 'http://localhost:8080',
    [string]$DocPath = 'test-data\java-threads.md'
)

$ErrorActionPreference = 'Stop'
$envFile = '.\docker\.env'
$adminPw = (Get-Content $envFile | Where-Object { $_ -match '^ADMIN_PASSWORD=' } | ForEach-Object { ($_ -split '=')[1] })

# 登录
$login = Invoke-RestMethod -Uri "$BaseUrl/api/user/login" -Method Post -Body (@{username='admin';password=$adminPw}|ConvertTo-Json) -ContentType 'application/json'
$headers = @{ satoken = $login.data }

# 创建测试知识库
$kb = Invoke-RestMethod -Uri "$BaseUrl/api/knowledge-base" -Method Post -Headers $headers -Body (@{name='Benchmark KB';description='性能测试'}|ConvertTo-Json) -ContentType 'application/json'
$kbId = $kb.data.id

$durations = @()

for ($i = 1; $i -le $Iterations; $i++) {
    Write-Host "[$i/$Iterations] 上传并解析文档..."
    $start = Get-Date
    
    # 上传
    $upJson = curl.exe -s -X POST "$BaseUrl/api/document/upload" -H "satoken: $($login.data)" -F "file=@$DocPath" -F "title=Bench-$i" -F "knowledgeBaseId=$kbId"
    $up = $upJson | ConvertFrom-Json
    $docId = $up.data.id
    
    # 触发解析
    curl.exe -s -X POST "$BaseUrl/api/document/$docId/parse" -H "satoken: $($login.data)" | Out-Null
    
    # 轮询直到完成
    while ($true) {
        Start-Sleep -Seconds 2
        $doc = (curl.exe -s "$BaseUrl/api/document/$docId" -H "satoken: $($login.data)") | ConvertFrom-Json
        if ($doc.data.status -eq 2) { break }  # COMPLETED
        if ($doc.data.status -eq 3) { throw "解析失败" }
    }
    
    $duration = ((Get-Date) - $start).TotalSeconds
    $durations += $duration
    Write-Host "  耗时: $([math]::Round($duration, 2))s"
}

# 统计
$avg = ($durations | Measure-Object -Average).Average
$p50 = $durations | Sort-Object | Select-Object -Index ([math]::Floor($durations.Count * 0.5))
$p95 = $durations | Sort-Object | Select-Object -Index ([math]::Floor($durations.Count * 0.95))

Write-Host "`n==== 文档处理性能 ===="
Write-Host "平均耗时: $([math]::Round($avg, 2))s"
Write-Host "P50 延迟: $([math]::Round($p50, 2))s"
Write-Host "P95 延迟: $([math]::Round($p95, 2))s"

# 清理
Invoke-RestMethod -Uri "$BaseUrl/api/knowledge-base/$kbId" -Method Delete -Headers $headers | Out-Null
```

**运行**：
```powershell
.\scripts\benchmark-document-pipeline.ps1 -Iterations 10
```

**基线目标**（3KB Markdown 文件）：
- 平均耗时：< 8s
- P95 延迟：< 12s
- 成功率：100%

---

### 2. RAG 检索性能

**测试脚本**：`scripts\benchmark-rag-retrieval.ps1`

```powershell
# benchmark-rag-retrieval.ps1
param(
    [int]$Iterations = 100,
    [string]$PythonUrl = 'http://localhost:9000',
    [int]$KnowledgeBaseId = 52
)

$ErrorActionPreference = 'Stop'
$envFile = '.\docker\.env'
$token = (Get-Content $envFile | Where-Object { $_ -match '^PYTHON_AI_INTERNAL_TOKEN=' } | ForEach-Object { ($_ -split '=')[1] })
$headers = @{ 'X-Internal-Token' = $token; 'X-Tenant-Id' = '1'; 'Content-Type' = 'application/json; charset=utf-8' }

$queries = @(
    'Java 虚拟线程如何工作',
    '如何配置 Milvus 向量数据库',
    'RAG 检索的最佳实践',
    'Agent 工作流的设计模式'
)

$durations = @()

for ($i = 1; $i -le $Iterations; $i++) {
    $query = $queries[$i % $queries.Count]
    $body = @{ query = $query; knowledge_base_id = $KnowledgeBaseId; top_k = 5 } | ConvertTo-Json
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    
    $start = Get-Date
    try {
        $r = Invoke-WebRequest -Uri "$PythonUrl/api/rag/debug/search" -Method Post -Headers $headers -Body $bodyBytes -UseBasicParsing -TimeoutSec 10
        $duration = ((Get-Date) - $start).TotalMilliseconds
        $durations += $duration
        
        if ($i % 10 -eq 0) {
            Write-Host "[$i/$Iterations] P95: $([math]::Round(($durations | Sort-Object | Select-Object -Index ([math]::Floor($durations.Count * 0.95))), 0))ms"
        }
    } catch {
        Write-Host "[FAIL] $query"
    }
}

$avg = ($durations | Measure-Object -Average).Average
$p50 = $durations | Sort-Object | Select-Object -Index ([math]::Floor($durations.Count * 0.5))
$p95 = $durations | Sort-Object | Select-Object -Index ([math]::Floor($durations.Count * 0.95))
$p99 = $durations | Sort-Object | Select-Object -Index ([math]::Floor($durations.Count * 0.99))

Write-Host "`n==== RAG 检索性能 ===="
Write-Host "请求数: $($durations.Count)"
Write-Host "平均延迟: $([math]::Round($avg, 0))ms"
Write-Host "P50 延迟: $([math]::Round($p50, 0))ms"
Write-Host "P95 延迟: $([math]::Round($p95, 0))ms"
Write-Host "P99 延迟: $([math]::Round($p99, 0))ms"
```

**运行**：
```powershell
# 前置：确保 KB 52 存在且有文档
.\scripts\benchmark-rag-retrieval.ps1 -Iterations 100 -KnowledgeBaseId 52
```

**基线目标**（KB 内含 50 文档，~1000 chunks）：
- 平均延迟：< 300ms
- P95 延迟：< 500ms
- P99 延迟：< 800ms

---

### 3. 聊天响应（含 RAG）

**JMeter 测试计划**：`scripts\chat-load-test.jmx`

关键配置：
- 线程数：10（并发用户）
- Ramp-up：10 秒
- 循环次数：10
- 请求：`POST /api/chat/stream`

**运行**：
```bash
jmeter -n -t scripts/chat-load-test.jmx -l results.jtl -e -o report/
```

**基线目标**：
- 吞吐量：> 2 请求/秒
- 平均响应时间：< 5s
- 错误率：< 1%

---

## Java 后端性能

### API 响应时间

**测试脚本**：`scripts\benchmark-java-api.ps1`

```powershell
# benchmark-java-api.ps1
param([string]$BaseUrl = 'http://localhost:8080')

$ErrorActionPreference = 'Stop'
$adminPw = (Get-Content '.\docker\.env' | Where-Object { $_ -match '^ADMIN_PASSWORD=' } | ForEach-Object { ($_ -split '=')[1] })
$login = Invoke-RestMethod -Uri "$BaseUrl/api/user/login" -Method Post -Body (@{username='admin';password=$adminPw}|ConvertTo-Json) -ContentType 'application/json'
$headers = @{ satoken = $login.data }

$endpoints = @(
    @{n='用户信息';p='/user/info'},
    @{n='知识库列表';p='/knowledge-base/my?page=1&pageSize=10'},
    @{n='对话列表';p='/conversation/my?page=1&pageSize=10'},
    @{n='用量汇总';p='/cost/summary?days=30'}
)

foreach ($ep in $endpoints) {
    $durations = @()
    for ($i = 1; $i -le 50; $i++) {
        $start = Get-Date
        Invoke-RestMethod -Uri "$BaseUrl/api$($ep.p)" -Headers $headers | Out-Null
        $durations += ((Get-Date) - $start).TotalMilliseconds
    }
    $avg = ($durations | Measure-Object -Average).Average
    $p95 = $durations | Sort-Object | Select-Object -Index 47
    Write-Host "$($ep.n): Avg=$([math]::Round($avg))ms, P95=$([math]::Round($p95))ms"
}
```

**基线目标**：
- 用户信息：< 50ms (P95)
- 知识库列表：< 100ms (P95)
- 对话列表：< 150ms (P95)

---

## Python AI 服务性能

### LLM 响应时间

```python
# scripts/benchmark_llm.py
import time
import asyncio
from app.core.llm import get_llm

async def benchmark_llm(iterations=20):
    llm = get_llm()
    durations = []
    
    for i in range(iterations):
        start = time.time()
        response = await llm.generate("用一句话解释什么是 RAG")
        duration = (time.time() - start) * 1000
        durations.append(duration)
        print(f"[{i+1}/{iterations}] {duration:.0f}ms")
    
    durations.sort()
    avg = sum(durations) / len(durations)
    p50 = durations[len(durations) // 2]
    p95 = durations[int(len(durations) * 0.95)]
    
    print(f"\n==== LLM 性能 ====")
    print(f"平均: {avg:.0f}ms")
    print(f"P50: {p50:.0f}ms")
    print(f"P95: {p95:.0f}ms")

if __name__ == "__main__":
    asyncio.run(benchmark_llm())
```

**运行**：
```bash
cd python-ai
.venv\Scripts\activate
python scripts/benchmark_llm.py
```

**基线目标**（DeepSeek API）：
- 平均：< 2000ms
- P95：< 3500ms

---

## 数据库性能

### 慢查询监控

启用 MySQL 慢查询日志：

```sql
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 0.5;  -- 超过 500ms 记录
SET GLOBAL slow_query_log_file = '/var/log/mysql/slow.log';
```

查询慢查询：
```bash
docker exec hfusionhub-mysql mysqldumpslow -s t -t 10 /var/log/mysql/slow.log
```

### 连接池监控

查看 HikariCP 指标（Actuator）：
```bash
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.idle
```

---

## 向量数据库性能

### Milvus 索引质量

```python
# scripts/check_milvus_index.py
from pymilvus import connections, Collection

connections.connect(host='localhost', port=19530)
collection = Collection('document_chunks')

print(f"Entity count: {collection.num_entities}")
print(f"Index: {collection.index().params}")

# 检索性能测试
import time
query_vector = [[0.1] * 1536]  # 示例向量
start = time.time()
results = collection.search(query_vector, "embedding", {"metric_type": "L2"}, limit=10)
print(f"Search latency: {(time.time() - start) * 1000:.0f}ms")
```

**基线目标**（100 万向量）：
- 检索延迟：< 50ms (P95)

---

## 前端性能

### Lighthouse 评分

```bash
cd hfusionhub-frontend
npm run build
npm run preview

# 使用 Chrome DevTools Lighthouse
# 或命令行：
npx lighthouse http://localhost:4173 --output html --output-path report.html
```

**基线目标**：
- Performance：> 90
- Accessibility：> 95
- Best Practices：> 90
- SEO：> 85

---

## 基线记录模板

```markdown
# 性能基线 — v1.0.0 (2026-08-19)

## 环境
- CPU: Intel i7-12700K (8P+4E)
- RAM: 32 GB DDR5
- Disk: Samsung 980 Pro NVMe
- OS: Windows 11

## 结果

| 指标 | 平均 | P95 | P99 | 目标 | 状态 |
|------|------|-----|-----|------|------|
| 文档处理端到端 | 7.2s | 9.8s | - | < 8s | ✅ |
| RAG 检索延迟 | 280ms | 420ms | 650ms | < 500ms | ✅ |
| 聊天响应（含 RAG） | 4.1s | 6.5s | - | < 5s | ⚠️ |
| 用户信息 API | 28ms | 45ms | - | < 50ms | ✅ |
| LLM 生成（DeepSeek） | 1850ms | 3200ms | - | < 3500ms | ✅ |
| Milvus 检索 | 32ms | 48ms | - | < 50ms | ✅ |

## 瓶颈
- 聊天响应 P95 超目标 30%，主因：LLM API 网络波动
```

---

## 回归测试

每次版本发布前运行全套基线测试，对比结果：

```powershell
.\scripts\run-all-benchmarks.ps1 > baseline-v1.1.0.txt
diff baseline-v1.0.0.txt baseline-v1.1.0.txt
```

---

**最后更新**：2026-08-19  
**相关文档**：[性能优化指南](./PERFORMANCE_TUNING.md)
