# 扩容与性能优化指南

> 本文档合并原 SCALING.md（扩容优化）与 PERFORMANCE_BASELINE.md（性能基线测试）为
> 唯一扩容与性能手册。按需查阅：扩容决策 → 垂直/水平扩容 → Kubernetes → 性能基线测试 → 监控告警。
>
> ⚠️ 本文中的 `docker-compose.scale.yml`、`nginx-lb.conf`、`milvus-cluster.yml`、
> `hfusionhub-chart/`、`alert-rules.yml` 等为**部署思路示例**，仓库实际文件为
> `deploy/docker-compose.prod.yml`、`deploy/nginx.conf`、`deploy/helm/hfusionhub/`、
> `deploy/monitoring/`（Prometheus 告警规则）——请以实际文件为准。

## 📊 性能基线测试（原 PERFORMANCE_BASELINE.md）

### 测试目标

建立 HFusionHub 各核心功能的性能基线，用于：
- 版本迭代对比（回归检测）
- 容量规划（资源评估）
- 瓶颈识别（优化方向）

### 测试环境要求

**硬件规格**：CPU 4 核 / 8 线程（最低）、内存 16 GB、SSD（NVMe 推荐）、千兆局域网。
**软件版本**：Docker 24.0+、JDK 21、Python 3.11、MySQL 8.0、Milvus 2.3+。
**初始状态**：空数据库（仅 admin 用户）、缓存已预热（启动后等待 30 秒）、无其他负载。

### 快速冒烟测试（5 分钟）

验证所有服务可用性：

```powershell
.\scripts\smoke-test.ps1
```

**预期结果**：`==== 结果: 47 PASS / 0 FAIL ====`

### 一键运行全套基线

项目提供统一基线脚本，会执行 Java API + RAG + 文档处理端到端基线测试：

```powershell
.\scripts\run-all-benchmarks.ps1
```

> 注意：仓库当前只提供 `smoke-test.ps1` 与 `run-all-benchmarks.ps1` 两个真实存在的
> 基准脚本。逐项细粒度压测（文档管线 / RAG 检索 / Java API 专项）可按下方示例在本地临时编写。

### 1. 文档上传→解析→向量化（端到端）基线目标

- **运行方式**：通过 `run-all-benchmarks.ps1` 或按下方示例临时脚本。
- **基线目标**（3KB Markdown 文件，10 次迭代）：
  - 平均耗时：< 8s
  - P95 延迟：< 12s
  - 成功率：100%

示例脚本（`benchmark-document-pipeline.ps1` 逻辑，需时可在本地保存复用）：

```powershell
param(
    [int]$Iterations = 10,
    [string]$BaseUrl = 'http://localhost:8080',
    [string]$DocPath = 'test-data\java-threads.md'
)
$ErrorActionPreference = 'Stop'
$envFile = '.\docker\.env'
$adminPw = (Get-Content $envFile | Where-Object { $_ -match '^ADMIN_PASSWORD=' } | ForEach-Object { ($_ -split '=')[1] })
$login = Invoke-RestMethod -Uri "$BaseUrl/api/user/login" -Method Post -Body (@{username='admin';password=$adminPw}|ConvertTo-Json) -ContentType 'application/json'
$headers = @{ satoken = $login.data }
$kb = Invoke-RestMethod -Uri "$BaseUrl/api/knowledge-base" -Method Post -Headers $headers -Body (@{name='Benchmark KB';description='性能测试'}|ConvertTo-Json) -ContentType 'application/json'
$kbId = $kb.data.id
$durations = @()
for ($i = 1; $i -le $Iterations; $i++) {
    Write-Host "[$i/$Iterations] 上传并解析文档..."
    $start = Get-Date
    $upJson = curl.exe -s -X POST "$BaseUrl/api/document/upload" -H "satoken: $($login.data)" -F "file=@$DocPath" -F "title=Bench-$i" -F "knowledgeBaseId=$kbId"
    $up = $upJson | ConvertFrom-Json
    $docId = $up.data.id
    curl.exe -s -X POST "$BaseUrl/api/document/$docId/parse" -H "satoken: $($login.data)" | Out-Null
    while ($true) {
        Start-Sleep -Seconds 2
        $doc = (curl.exe -s "$BaseUrl/api/document/$docId" -H "satoken: $($login.data)") | ConvertFrom-Json
        if ($doc.data.status -eq 2) { break }
        if ($doc.data.status -eq 3) { throw "解析失败" }
    }
    $duration = ((Get-Date) - $start).TotalSeconds
    $durations += $duration
    Write-Host "  耗时: $([math]::Round($duration, 2))s"
}
$avg = ($durations | Measure-Object -Average).Average
$p50 = $durations | Sort-Object | Select-Object -Index ([math]::Floor($durations.Count * 0.5))
$p95 = $durations | Sort-Object | Select-Object -Index ([math]::Floor($durations.Count * 0.95))
Write-Host "`n==== 文档处理性能 ===="
Write-Host "平均耗时: $([math]::Round($avg, 2))s"
Write-Host "P50 延迟: $([math]::Round($p50, 2))s"
Write-Host "P95 延迟: $([math]::Round($p95, 2))s"
Invoke-RestMethod -Uri "$BaseUrl/api/knowledge-base/$kbId" -Method Delete -Headers $headers | Out-Null
```

### 2. RAG 检索性能基线目标

- **运行方式**：`POST $PythonUrl/api/rag/debug/search`（X-Internal-Token + X-Tenant-Id 头），100 次迭代，查询池 4 条，`top_k=5`。
- **前置**：KB 52 存在且有文档。
- **基线目标**（KB 内含 50 文档，~1000 chunks）：
  - 平均延迟：< 300ms
  - P95 延迟：< 500ms
  - P99 延迟：< 800ms

### 3. Java 后端 API 响应基线目标

- **运行方式**：登录后对核心端点（`/user/info`、`/knowledge-base/my`、`/conversation/my`、`/cost/summary`）各请求 50 次。
- **基线目标**：用户信息 < 50ms (P95)、知识库列表 < 100ms (P95)、对话列表 < 150ms (P95)。

### 4. LLM 生成基线目标

- **运行方式**：`cd python-ai && .venv\Scripts\activate && python -m app.benchmark.llm`（或在本地临时编写调用 `get_llm().generate()` 的脚本，20 次迭代）。
- **基线目标**（DeepSeek API）：平均 < 2000ms、P95 < 3500ms。

### 5. 向量检索基线目标

- **运行方式**：Milvus `collection.search()` 或通过 RAG debug/search。
- **基线目标**（100 万向量）：检索延迟 < 50ms (P95)。

### 6. 前端 Lighthouse 基线目标

```bash
cd hfusionhub-frontend
npm run build && npm run preview
npx lighthouse http://localhost:4173 --output html --output-path report.html
```

**基线目标**：Performance > 90、Accessibility > 95、Best Practices > 90、SEO > 85。

### 基线记录模板

```markdown
# 性能基线 — v1.0.0 (2026-08-19)

## 环境
- CPU: Intel i7-12700K (8P+4E) / RAM: 32 GB DDR5 / Disk: Samsung 980 Pro NVMe / OS: Windows 11

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

### 回归测试

每次版本发布前运行全套基线测试，对比结果：

```powershell
.\scripts\run-all-benchmarks.ps1 > baseline-v1.1.0.txt
diff baseline-v1.0.0.txt baseline-v1.1.0.txt
```

### 慢查询与连接池监控

```sql
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 0.5;  -- 超过 500ms 记录
SET GLOBAL slow_query_log_file = '/var/log/mysql/slow.log';
```

```bash
docker exec hfusionhub-mysql mysqldumpslow -s t -t 10 /var/log/mysql/slow.log
curl http://localhost:8080/api/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/api/actuator/metrics/hikaricp.connections.idle
```

---

## 📈 扩容决策矩阵

根据监控指标决定扩容时机：

| 指标 | 阈值 | 行动 |
|------|------|------|
| CPU 持续使用率 | > 70% | 垂直扩容（增加核心数）|
| 内存使用率 | > 80% | 垂直扩容（增加内存）|
| 数据库连接池 | > 80% 使用率 | 增加连接数或读写分离 |
| 向量数据量 | > 100 万条 | Milvus 分片优化 |
| 并发用户 | > 100 | 水平扩容（多实例） |
| 磁盘使用率 | > 85% | 扩容存储或归档旧数据 |

---

## 🔧 垂直扩容（单机优化）

### Java 后端优化

#### 1. JVM 参数调优

编辑 `java-backend/src/main/resources/application.yml`：

```bash
# 启动参数（4 核 16 GB 机器）
java -Xms4g -Xmx8g \
     -XX:+UseG1GC \
     -XX:MaxGCPauseMillis=200 \
     -XX:+UseStringDeduplication \
     -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/var/log/hfusionhub/heapdump.hprof \
     -jar hfusionhub-backend.jar
```

**参数说明**：
- `-Xms4g`：初始堆 4 GB
- `-Xmx8g`：最大堆 8 GB（物理内存的 50%）
- `UseG1GC`：G1 垃圾回收器（推荐）
- `MaxGCPauseMillis=200`：目标 GC 暂停 < 200ms

#### 2. 数据库连接池

```yaml
# application.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 50        # 增加到 50（原 20）
      minimum-idle: 10             # 保持 10 个空闲连接
      connection-timeout: 30000    # 30 秒超时
      idle-timeout: 600000         # 10 分钟空闲回收
      max-lifetime: 1800000        # 30 分钟最大生命周期
      leak-detection-threshold: 60000  # 连接泄漏检测
```

**监控**：
```bash
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.usage
```

#### 3. 虚拟线程池

已默认启用（Spring Boot 3.2+），无需额外配置。监控：
```bash
curl http://localhost:8080/actuator/metrics/executor.active
```

---

### Python AI 优化

#### 1. Worker 进程数

```bash
# python-ai/.env
WEB_CONCURRENCY=8  # CPU 核心数（原 4）

# 或启动时指定
uvicorn app.main:app --workers 8 --host 0.0.0.0 --port 9000
```

**推荐配置**：
- 4 核：4 workers
- 8 核：6-8 workers
- 16 核：12-16 workers

#### 2. Embedding 批处理

```bash
# python-ai/.env
EMBEDDING_BATCH_SIZE=64  # 增加批处理（原 16）
```

#### 3. LLM 连接池

```python
# app/core/llm/deepseek_llm.py
# 增加异步客户端连接池
httpx.AsyncClient(
    timeout=httpx.Timeout(60.0),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
)
```

---

### MySQL 优化

#### 1. InnoDB 缓冲池

```sql
-- 查看当前配置
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';

-- 设置为物理内存的 70%（16 GB 机器 → 11 GB）
SET GLOBAL innodb_buffer_pool_size = 11811160064;
```

永久配置（`docker-compose.yml`）：
```yaml
mysql:
  command:
    - --innodb-buffer-pool-size=11G
    - --innodb-log-file-size=512M
    - --max-connections=500
```

#### 2. 查询缓存与索引

```sql
-- 分析慢查询
SELECT * FROM mysql.slow_log ORDER BY query_time DESC LIMIT 10;

-- 添加缺失索引（示例）
ALTER TABLE message ADD INDEX idx_conversation_created (conversation_id, created_at);
ALTER TABLE document_chunk ADD INDEX idx_document_id (document_id);
```

---

### Milvus 优化

#### 1. 索引参数调优

```python
# 对于 > 100 万向量，调整 HNSW 参数
from pymilvus import Collection, connections

connections.connect(host='localhost', port=19530)
collection = Collection('document_chunks')

# 重建索引
collection.drop_index()
index_params = {
    "metric_type": "L2",
    "index_type": "HNSW",
    "params": {
        "M": 32,              # 增加邻居数（原 16）
        "efConstruction": 400  # 增加构建精度（原 200）
    }
}
collection.create_index(field_name="embedding", index_params=index_params)
```

**权衡**：
- `M` 越大：检索精度越高，但内存占用越大
- `efConstruction` 越大：索引质量越高，但构建时间越长

#### 2. 检索参数

```python
# app/core/rag/retriever/vector_retriever.py
search_params = {
    "metric_type": "L2",
    "params": {
        "ef": 128  # 增加搜索范围（原 64）
    }
}
```

#### 3. 内存限制

```yaml
# docker-compose.yml
milvus:
  deploy:
    resources:
      limits:
        memory: 8G   # 增加到 8 GB（原 4 GB）
```

---

### Redis 优化

#### 1. 内存策略

```bash
# redis.conf
maxmemory 4gb
maxmemory-policy allkeys-lru  # LRU 淘汰策略
```

#### 2. 持久化优化

```bash
# 减少 RDB 频率（适合缓存场景）
save 900 1
save 3600 10

# AOF 每秒同步（平衡性能与持久性）
appendfsync everysec
```

---

## 📦 水平扩容（多实例部署）

### Java 后端水平扩容

#### 1. 无状态设计验证

确保会话存储在 Redis（已实现）：
```yaml
# application.yml
sa-token:
  token-style: jwt
  jwt-secret-key: ${SA_TOKEN_JWT_SECRET_KEY}
  is-share: true  # 跨实例共享
```

#### 2. 部署多实例（Docker Compose）

```yaml
# deploy/docker-compose.scale.yml
version: '3.8'
services:
  java-backend-1:
    image: hfusionhub/backend:latest
    ports:
      - "8081:8080"
    environment:
      - INSTANCE_ID=backend-1
  
  java-backend-2:
    image: hfusionhub/backend:latest
    ports:
      - "8082:8080"
    environment:
      - INSTANCE_ID=backend-2
  
  nginx:
    image: nginx:latest
    ports:
      - "8080:80"
    volumes:
      - ./nginx-lb.conf:/etc/nginx/nginx.conf
```

#### 3. Nginx 负载均衡

```nginx
# deploy/nginx-lb.conf
upstream java_backend {
    least_conn;  # 最少连接负载均衡
    server java-backend-1:8080 max_fails=3 fail_timeout=30s;
    server java-backend-2:8080 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    
    location /api {
        proxy_pass http://java_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
    }
}
```

---

### Python AI 水平扩容

#### 部署多实例

```yaml
# deploy/docker-compose.scale.yml
services:
  python-ai-1:
    image: hfusionhub/python-ai:latest
    ports:
      - "9001:9000"
  
  python-ai-2:
    image: hfusionhub/python-ai:latest
    ports:
      - "9002:9000"
```

#### Java 后端配置多个 AI 服务地址

```java
// com/hfusionhub/client/AiClient.java
@Value("${ai.service.urls}")
private List<String> aiServiceUrls;  // http://python-ai-1:9000,http://python-ai-2:9000

// 实现简单轮询或随机选择
private String selectAiServiceUrl() {
    return aiServiceUrls.get(new Random().nextInt(aiServiceUrls.size()));
}
```

---

### MySQL 读写分离

#### 1. 主从复制配置

**主库（docker-compose.yml）**：
```yaml
mysql-master:
  image: mysql:8.0
  command:
    - --server-id=1
    - --log-bin=mysql-bin
    - --binlog-format=ROW
```

**从库**：
```yaml
mysql-slave:
  image: mysql:8.0
  command:
    - --server-id=2
    - --relay-log=mysql-relay-bin
```

#### 2. 配置主从同步

```sql
-- 主库创建同步用户
CREATE USER 'replicator'@'%' IDENTIFIED BY 'strong_password';
GRANT REPLICATION SLAVE ON *.* TO 'replicator'@'%';
FLUSH PRIVILEGES;

-- 从库配置
CHANGE MASTER TO
  MASTER_HOST='mysql-master',
  MASTER_USER='replicator',
  MASTER_PASSWORD='strong_password',
  MASTER_LOG_FILE='mysql-bin.000001',
  MASTER_LOG_POS=0;

START SLAVE;
SHOW SLAVE STATUS\G
```

#### 3. MyBatis Plus 读写分离

```yaml
# application.yml
spring:
  datasource:
    master:
      url: jdbc:mysql://mysql-master:3306/hfusionhub_db
    slave:
      url: jdbc:mysql://mysql-slave:3306/hfusionhub_db
```

---

### Milvus 分片扩容

#### 集群模式部署

```yaml
# deploy/milvus-cluster.yml
services:
  milvus-proxy:
    image: milvusdb/milvus:v2.3.0
    command: milvus run proxy
  
  milvus-querynode-1:
    image: milvusdb/milvus:v2.3.0
    command: milvus run querynode
  
  milvus-querynode-2:
    image: milvusdb/milvus:v2.3.0
    command: milvus run querynode
  
  milvus-datanode:
    image: milvusdb/milvus:v2.3.0
    command: milvus run datanode
```

---

## 📊 Kubernetes 部署（推荐生产环境）

### Helm Chart 部署

```bash
# 使用项目提供的 Helm Chart
cd deploy/helm
helm install hfusionhub ./hfusionhub \
  --namespace hfusionhub \
  --create-namespace \
  --values production-values.yaml
```

### HPA（水平 Pod 自动扩展）

```yaml
# deploy/helm/hfusionhub/templates/hpa.yaml（示例）
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: java-backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: java-backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

## 🔍 性能监控与告警

### Prometheus 指标

关键指标：
```promql
# Java 后端 QPS
rate(http_server_requests_seconds_count[1m])

# 响应时间 P95
histogram_quantile(0.95, rate(http_server_requests_seconds_bucket[5m]))

# 数据库连接池使用率
hikaricp_connections_active / hikaricp_connections_max

# JVM 堆使用率
jvm_memory_used_bytes{area="heap"} / jvm_memory_max_bytes{area="heap"}
```

### Grafana 告警规则

```yaml
# deploy/monitoring/alert-rules.yml
groups:
  - name: hfusionhub
    interval: 30s
    rules:
      - alert: HighCPUUsage
        expr: rate(process_cpu_usage[1m]) > 0.8
        for: 5m
        annotations:
          summary: "CPU 使用率 > 80%"
      
      - alert: HighMemoryUsage
        expr: jvm_memory_used_bytes / jvm_memory_max_bytes > 0.9
        for: 5m
        annotations:
          summary: "内存使用率 > 90%"
      
      - alert: SlowAPIResponse
        expr: histogram_quantile(0.95, rate(http_server_requests_seconds_bucket[5m])) > 1
        for: 10m
        annotations:
          summary: "API P95 响应时间 > 1s"
```

---

## 📋 扩容检查清单

### 扩容前
- [ ] 备份所有数据（MySQL + Milvus + MinIO）
- [ ] 记录当前性能基线
- [ ] 准备回滚方案
- [ ] 通知用户（如需停机）

### 扩容中
- [ ] 按步骤执行（先垂直后水平）
- [ ] 监控关键指标
- [ ] 验证功能正常

### 扩容后
- [ ] 运行冒烟测试
- [ ] 压力测试验证
- [ ] 更新文档
- [ ] 保留旧配置 7 天

---

## 💰 成本优化

### 资源使用优化

1. **定期清理过期数据**
   ```sql
   -- 删除 90 天前的用量记录
   DELETE FROM model_usage_record WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY);
   
   -- 清理回收站文档（30 天）
   DELETE FROM document WHERE deleted_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
   ```

2. **MinIO 生命周期策略**
   ```bash
   mc ilm add local/hfusionhub --expiry-days 365 --prefix "uploads/temp/"
   ```

3. **Redis 内存优化**
   ```bash
   # 启用压缩
   redis-cli CONFIG SET list-compress-depth 1
   ```

---

**最后更新**：2026-08-19  
**相关文档**：[PRODUCTION_OPS.md](PRODUCTION_OPS.md)（含生产检查清单）、[TROUBLESHOOTING.md](TROUBLESHOOTING.md)
