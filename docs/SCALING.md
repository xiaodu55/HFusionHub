# 扩容与性能优化指南

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
helm install hfusionhub ./hfusionhub-chart \
  --namespace hfusionhub \
  --create-namespace \
  --values production-values.yaml
```

### HPA（水平 Pod 自动扩展）

```yaml
# deploy/helm/hfusionhub-chart/templates/hpa.yaml
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
**相关文档**：[性能基线测试](./PERFORMANCE_BASELINE.md)、[生产环境检查清单](./PRODUCTION_CHECKLIST.md)
