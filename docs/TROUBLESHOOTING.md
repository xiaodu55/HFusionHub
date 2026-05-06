# 故障排查手册

## 🚨 快速诊断流程

1. **检查所有服务状态**
   ```bash
   docker ps
   ```
   预期：7 个容器运行中（mysql, redis, minio, milvus, etcd, attu, plugin-runner）

2. **查看服务日志**
   ```bash
   # Java 后端
   cd java-backend && tail -f logs/spring.log
   
   # Python AI
   cd python-ai && tail -f logs/app.log
   
   # 前端（开发模式）
   cd hfusionhub-frontend && npm run dev
   
   # Docker 服务
   docker logs -f hfusionhub-mysql
   docker logs -f hfusionhub-redis
   docker logs -f hfusionhub-milvus
   ```

3. **运行健康检查**
   ```powershell
   .\scripts\smoke-test.ps1 -Quick
   ```

---

## 常见问题分类

### 🔴 P0 — 服务完全不可用

#### 1. 所有服务无法启动

**症状**：`docker compose up -d` 失败

**可能原因**：
- Docker Desktop 未启动
- 端口被占用（3306, 6379, 8080, 9000, 3000, 19530）
- 磁盘空间不足

**诊断**：
```bash
# 检查端口占用
netstat -ano | findstr "3306 6379 8080 9000"

# 检查磁盘空间
docker system df
```

**解决**：
```bash
# 停止占用端口的进程（管理员权限）
taskkill /PID <PID> /F

# 清理 Docker 磁盘（谨慎！）
docker system prune -a --volumes
```

---

#### 2. Java 后端启动失败

**症状**：`mvn spring-boot:run` 报错退出

**常见错误 A：数据库连接失败**
```
Could not open JDBC Connection for transaction
```

**诊断**：
```bash
# 检查 MySQL 是否运行
docker ps | grep mysql

# 测试连接
docker exec hfusionhub-mysql mysql -uroot -p<密码> -e "SELECT 1"
```

**解决**：
```bash
# 重启 MySQL
docker restart hfusionhub-mysql

# 检查密码是否匹配 docker/.env 中的 MYSQL_ROOT_PASSWORD
```

**常见错误 B：Flyway 迁移失败**
```
Migration V57__user_theme_preference.sql failed
```

**诊断**：
```sql
-- 查看迁移历史
docker exec hfusionhub-mysql mysql -uhfusionhub -p<密码> hfusionhub_db \
  -e "SELECT * FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 5"
```

**解决**：
```sql
-- 如果迁移卡住，手动标记为成功（谨慎！）
docker exec hfusionhub-mysql mysql -uroot -p<密码> hfusionhub_db \
  -e "UPDATE flyway_schema_history SET success=1 WHERE version='57'"

-- 或删除失败记录后重启
docker exec hfusionhub-mysql mysql -uroot -p<密码> hfusionhub_db \
  -e "DELETE FROM flyway_schema_history WHERE version='57' AND success=0"
```

**常见错误 C：端口 8080 已被占用**
```
Port 8080 was already in use
```

**解决**：
```bash
# 找到占用进程
netstat -ano | findstr ":8080"
taskkill /PID <PID> /F

# 或修改端口
# application.yml → server.port: 8081
```

---

#### 3. Python AI 服务启动失败

**症状**：`python -m app.main` 报错退出

**常见错误 A：Redis 连接失败**
```
ConnectionError: Error 111 connecting to localhost:6379
```

**解决**：
```bash
docker restart hfusionhub-redis

# 检查 REDIS_PASSWORD 是否匹配 docker/.env
```

**常见错误 B：Milvus 连接失败**
```
MilvusException: <MilvusException: (code=1, message=Fail connecting to server)>
```

**诊断**：
```bash
# 检查 Milvus 是否运行
docker logs hfusionhub-milvus | tail -20

# 检查 etcd 是否健康
docker exec hfusionhub-etcd etcdctl endpoint health
```

**解决**：
```bash
# 重启 Milvus 栈
docker restart hfusionhub-etcd
sleep 5
docker restart hfusionhub-milvus

# 如果仍失败，重建容器
cd docker && docker compose down milvus etcd
docker compose up -d milvus etcd
```

**常见错误 C：依赖包缺失**
```
ModuleNotFoundError: No module named 'langchain'
```

**解决**：
```bash
cd python-ai
.venv\Scripts\activate
pip install -r requirements.txt
```

---

#### 4. 前端无法访问

**症状**：浏览器 `http://localhost:3000` 无响应

**常见错误 A：开发服务器未启动**

**解决**：
```bash
cd hfusionhub-frontend
npm run dev
```

**常见错误 B：端口 3000 被占用**

**解决**：
```bash
# 找到占用进程
netstat -ano | findstr ":3000"
taskkill /PID <PID> /F

# 或修改端口
# vite.config.ts → server.port: 3001
```

**常见错误 C：依赖包未安装**
```
Error: Cannot find module '@vitejs/plugin-vue'
```

**解决**：
```bash
cd hfusionhub-frontend
npm ci
```

---

### 🟠 P1 — 功能异常

#### 5. 登录失败（403 / 401）

**症状**：输入正确密码仍提示"用户名或密码错误"

**原因**：ADMIN_PASSWORD 与数据库不匹配

**解决**：
```sql
-- 查看当前 admin 密码哈希
docker exec hfusionhub-mysql mysql -uhfusionhub -p<密码> hfusionhub_db \
  -e "SELECT username, password FROM sys_user WHERE username='admin'"

-- 重置密码（BCrypt 哈希，对应 'admin123'）
docker exec hfusionhub-mysql mysql -uroot -p<密码> hfusionhub_db \
  -e "UPDATE sys_user SET password='\$2a\$10\$N9qo8uLOickgx2ZMRZoMye3K7i6M/xbJvbP3lIkRVwB2Y1V8VdYR2' WHERE username='admin'"
```

---

#### 6. 文档上传后解析卡住

**症状**：文档状态永远停留在 PROCESSING

**原因**：Python AI 服务未收到解析请求或 Milvus 不可用

**诊断**：
```bash
# 查看 Python AI 日志
cd python-ai && tail -f logs/app.log | grep "parse"

# 检查 document_index_job 表
docker exec hfusionhub-mysql mysql -uhfusionhub -p<密码> hfusionhub_db \
  -e "SELECT id, document_id, status, error_message FROM document_index_job ORDER BY id DESC LIMIT 5"
```

**解决**：
```bash
# 手动触发恢复调度器（或等待 5 分钟自动运行）
curl -X POST http://localhost:8080/actuator/scheduledtasks

# 如果 Milvus 有问题，重启后重新解析
docker restart hfusionhub-milvus
# 前端点击"重新解析"按钮
```

---

#### 7. 聊天无响应或报错

**症状**：发送消息后长时间无反应或 500 错误

**常见原因 A：DeepSeek API Key 无效**

**诊断**：
```bash
cd python-ai
.venv\Scripts\activate
python -c "from app.utils.config import config; print(config.DEEPSEEK_API_KEY)"
```

**解决**：
```bash
# 编辑 python-ai/.env
DEEPSEEK_API_KEY=sk-your-real-key

# 重启 Python 服务
python -m app.main
```

**常见原因 B：知识库无文档**

**诊断**：前端检查知识库是否已解析完成文档

**解决**：上传并等待文档解析完成

**常见原因 C：RAG 检索失败**

**诊断**：
```bash
# 测试检索接口
$headers = @{ 'X-Internal-Token' = '<token>'; 'X-Tenant-Id' = '1' }
$body = @{ query = '测试'; knowledge_base_id = 52; top_k = 3 } | ConvertTo-Json
Invoke-WebRequest -Uri "http://localhost:9000/api/rag/debug/search" -Method Post -Headers $headers -Body $body -ContentType 'application/json'
```

---

#### 8. 向量检索结果不准确

**症状**：聊天答非所问，引用文档不相关

**原因**：
- 文档质量差（格式混乱、无意义内容）
- Embedding 模型不匹配
- top_k 过小

**解决**：
```python
# 调整检索参数（python-ai/.env）
RAG_TOP_K=10              # 增加召回数量
RAG_RERANK_ENABLED=true   # 启用重排序
RAG_RERANK_TOP_N=5        # 重排后保留 5 个

# 重启 Python 服务
```

---

### 🟡 P2 — 性能问题

#### 9. 文档解析速度慢（> 30 秒）

**原因**：
- 文档过大（> 10 MB）
- Embedding 模型推理慢
- Milvus 写入慢

**诊断**：
```bash
# 查看 Python AI 日志中的耗时
cd python-ai && grep "parse_document took" logs/app.log

# 检查 Milvus CPU/内存占用
docker stats hfusionhub-milvus
```

**解决**：
```bash
# 优化 Embedding 批处理大小
# python-ai/.env
EMBEDDING_BATCH_SIZE=32  # 增加批处理

# 优化 Milvus 写入批次
MILVUS_BATCH_SIZE=1000
```

---

#### 10. 聊天响应慢（> 10 秒）

**原因**：
- DeepSeek API 网络延迟
- RAG 检索慢
- LLM 生成速度慢

**诊断**：
```bash
# 查看 RAG 追踪（前端 RAG 可观测页面）
# 或直接查询
curl http://localhost:8080/api/rag/traces?limit=10
```

**解决**：
```python
# 减少检索数量
RAG_TOP_K=5

# 启用缓存
RAG_CACHE_ENABLED=true

# 切换到本地 Ollama（速度可能更快）
LLM_PROVIDER=ollama
```

---

#### 11. 数据库查询慢

**诊断**：
```sql
-- 查看慢查询
docker exec hfusionhub-mysql mysql -uroot -p<密码> hfusionhub_db \
  -e "SHOW FULL PROCESSLIST"

-- 查看表大小
docker exec hfusionhub-mysql mysql -uroot -p<密码> hfusionhub_db \
  -e "SELECT table_name, ROUND((data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)' FROM information_schema.TABLES WHERE table_schema='hfusionhub_db' ORDER BY (data_length + index_length) DESC"
```

**解决**：
```sql
-- 添加索引（示例：message 表的 conversation_id）
ALTER TABLE message ADD INDEX idx_conversation_id (conversation_id);

-- 清理旧数据（示例：删除 90 天前的日志）
DELETE FROM model_usage_record WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY);
```

---

### 🟢 P3 — 非关键问题

#### 12. Swagger UI 无法访问

**症状**：`http://localhost:8080/swagger-ui/index.html` 404

**原因**：依赖未添加或 profile 禁用了

**解决**：
```xml
<!-- pom.xml 确保存在 -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.2.0</version>
</dependency>
```

```yaml
# application.yml
springdoc:
  swagger-ui:
    enabled: true
```

---

#### 13. 前端控制台 CORS 错误

**症状**：
```
Access to XMLHttpRequest at 'http://localhost:8080/api/user/info' from origin 'http://localhost:3000' has been blocked by CORS policy
```

**原因**：Java 后端 CORS 配置未包含前端域名

**解决**：
```bash
# 编辑 docker/.env
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# 重启 Java 后端
```

---

#### 14. Attu（Milvus UI）无法访问

**症状**：`http://localhost:8000` 无响应

**原因**：Attu 容器未启动

**解决**：
```bash
docker restart hfusionhub-attu

# 或重新创建
cd docker && docker compose up -d attu
```

---

## 数据恢复

### MySQL 备份与恢复

**备份**：
```bash
docker exec hfusionhub-mysql mysqldump -uroot -p<密码> hfusionhub_db > backup-$(date +%Y%m%d).sql
```

**恢复**：
```bash
docker exec -i hfusionhub-mysql mysql -uroot -p<密码> hfusionhub_db < backup-20260819.sql
```

### Milvus 数据重建

**如果 Milvus 数据损坏**：
```bash
# 停止 Milvus
docker compose down milvus

# 删除数据卷（⚠️ 危险操作）
docker volume rm docker_milvus-data

# 重新启动
docker compose up -d milvus

# 前端批量重新解析所有文档（设置页 → 系统维护 → 重建索引）
```

---

## 日志收集

**问题报告前请收集**：

```bash
# 创建诊断包
mkdir hfusionhub-diagnostics
cd hfusionhub-diagnostics

# Docker 容器状态
docker ps -a > docker-ps.txt
docker compose logs --tail=500 > docker-logs.txt

# Java 日志
cp ../java-backend/logs/spring.log java-backend.log

# Python 日志
cp ../python-ai/logs/app.log python-ai.log

# 系统信息
systeminfo > systeminfo.txt  # Windows
# uname -a > systeminfo.txt  # Linux

# 打包
tar -czf diagnostics-$(date +%Y%m%d-%H%M%S).tar.gz *
```

---

## 紧急联系方式

| 问题类型 | 联系人 | 响应时间 |
|---------|--------|----------|
| 服务宕机（P0） | 技术负责人 | < 30 分钟 |
| 数据丢失（P0） | DBA | < 1 小时 |
| 功能异常（P1） | 后端开发 | < 4 小时 |
| 性能问题（P2） | 运维工程师 | < 1 工作日 |

---

**最后更新**：2026-08-19  
**版本**：v1.0  
**维护者**：HFusionHub Team
