# 故障排查手册

## 🚨 快速诊断流程

1. **检查所有服务状态**
   ```bash
   docker ps
   ```
   预期：7 个容器运行中（mysql, redis, minio, milvus, etcd, attu, plugin-runner）

2. **查看服务日志**
   ```bash
   # Java 后端（restart-modules.ps1 启动时重定向到模块目录的 <module>-live.log）
   cd java-backend && tail -f java-live.log

   # Python AI
   cd python-ai && tail -f python-live.log

   # 前端（开发模式）
   cd hfusionhub-frontend && npm run dev

   # Docker 服务
   docker logs -f mysql8
   docker logs -f redis7
   docker logs -f milvus
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
docker exec mysql8 mysql -uroot -p<密码> -e "SELECT 1"
```

**解决**：
```bash
# 重启 MySQL
docker restart mysql8

# 检查密码是否匹配 docker/.env 中的 MYSQL_ROOT_PASSWORD
```

**常见错误 B：Flyway 迁移失败**
```
Migration V57__user_theme_preference.sql failed
```

**诊断**：
```sql
-- 查看迁移历史
docker exec mysql8 mysql -uhfusionhub -p<密码> hfusionhub \
  -e "SELECT * FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 5"
```

**解决**：
```sql
-- 如果迁移卡住，手动标记为成功（谨慎！）
docker exec mysql8 mysql -uroot -p<密码> hfusionhub \
  -e "UPDATE flyway_schema_history SET success=1 WHERE version='57'"

-- 或删除失败记录后重启
docker exec mysql8 mysql -uroot -p<密码> hfusionhub \
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
docker restart redis7

# 检查 REDIS_PASSWORD 是否匹配 docker/.env
```

**常见错误 B：Milvus 连接失败**
```
MilvusException: <MilvusException: (code=1, message=Fail connecting to server)>
```

**诊断**：
```bash
# 检查 Milvus 是否运行
docker logs milvus | tail -20

# 检查 etcd 是否健康
docker exec etcd etcdctl endpoint health
```

**解决**：
```bash
# 重启 Milvus 栈
docker restart etcd
sleep 5
docker restart milvus

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
docker exec mysql8 mysql -uhfusionhub -p<密码> hfusionhub \
  -e "SELECT username, password FROM sys_user WHERE username='admin'"

-- 重置密码（BCrypt 哈希，对应 'admin123'）
docker exec mysql8 mysql -uroot -p<密码> hfusionhub \
  -e "UPDATE sys_user SET password='\$2a\$10\$N9qo8uLOickgx2ZMRZoMye3K7i6M/xbJvbP3lIkRVwB2Y1V8VdYR2' WHERE username='admin'"
```

---

#### 6. 文档上传后解析卡住

**症状**：文档状态永远停留在 PROCESSING

**原因**：Python AI 服务未收到解析请求或 Milvus 不可用

**诊断**：
```bash
# 查看 Python AI 日志
cd python-ai && tail -f python-live.log | grep "parse"

# 检查 document_index_job 表
docker exec mysql8 mysql -uhfusionhub -p<密码> hfusionhub \
  -e "SELECT id, document_id, status, error_message FROM document_index_job ORDER BY id DESC LIMIT 5"
```

**解决**：
```bash
# 手动触发恢复调度器（或等待 5 分钟自动运行）
# 观察 DocumentIndexRecovery 等调度器是否在跑（注意 context-path 是 /api）
curl http://localhost:8080/api/actuator/health

# 如果 Milvus 有问题，重启后重新解析
docker restart milvus
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

#### 8.1 Java 调 Python 报 `400 Invalid HTTP request received.`（关键）

**症状**：文档解析、聊天、向量化全部失败；Python 日志显示 `400 Invalid HTTP request received.`

**根因**：Java 的 [RestTemplateConfig.java](../java-backend/src/main/java/com/hfusionhub/config/RestTemplateConfig.java) 使用 `JdkClientHttpRequestFactory`（JDK HttpClient），其**默认 HTTP/2**。对明文 `http://` 地址，JDK HttpClient 会发送 `Connection: Upgrade, HTTP2-Settings` + `Upgrade: h2c` 探测头；uvicorn 的 h11 解析器不支持 h2c，直接返回 400。仅 JDK HttpClient 有此行为（`HttpURLConnection` 无此问题）。

**解决**：已显式锁定 `.version(HttpClient.Version.HTTP_1_1)`（2026-08-21 修复，提交 05751c5）。若升级依赖后复现，检查 RestTemplate 底层是否仍是 JDK HttpClient 且锁定 HTTP/1.1。

---

#### 8.2 `restart-modules.ps1` 报 healthy 但服务没起来

**症状**：脚本输出 `[ok] java healthy`、`All requested modules restarted and healthy.`，但实际 8080/9000 没服务。

**根因**：PowerShell 5.1 的 `-File` 模式下，`-Modules java,python` 被绑定成**单个字符串** `'java,python'` 而非数组（只有 `-Command` 模式才按逗号拆成数组），导致 `ContainsKey` 全部 miss、所有模块被静默跳过。

**解决**：已修复（脚本内 `-split ','` 归一化，2026-08-21，提交 1aa868b）。升级脚本后重试。注意 `-Modules runner` 与 compose 容器端口冲突，重启 runner 用 `docker compose restart plugin-runner`。

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
cd python-ai && grep "parse_document took" python-live.log

# 检查 Milvus CPU/内存占用
docker stats milvus
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
docker exec mysql8 mysql -uroot -p<密码> hfusionhub \
  -e "SHOW FULL PROCESSLIST"

-- 查看表大小
docker exec mysql8 mysql -uroot -p<密码> hfusionhub \
  -e "SELECT table_name, ROUND((data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)' FROM information_schema.TABLES WHERE table_schema='hfusionhub' ORDER BY (data_length + index_length) DESC"
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

**症状**：`http://localhost:8080/api/swagger-ui/index.html` 404

**原因**：依赖未添加或 profile 禁用了（注意 Java 的 context-path 是 `/api`，项目用的是 Knife4j，主入口是 `http://localhost:8080/api/doc.html`）

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
docker restart attu

# 或重新创建
cd docker && docker compose up -d attu
```

---

## 数据恢复

### MySQL 备份与恢复

**备份**：
```bash
docker exec mysql8 mysqldump -uroot -p<密码> hfusionhub > backup-$(date +%Y%m%d).sql
```

**恢复**：
```bash
docker exec -i mysql8 mysql -uroot -p<密码> hfusionhub < backup-20260819.sql
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

### RAG 空库恢复（向量库被清，检索 0 sources）

**症状**：聊天 `Retrieved 0 sources`，但文档状态显示 COMPLETED。

**判断**：Milvus 集合 `hfusionhub_chunks` 实体数 = 0，MySQL `document_chunk` 仍有数据 → 向量库/源文件被清空（容器重建、卷漂移）。

**恢复**：
1. 检查向量库（Attu http://localhost:8000 或 Python）：
   ```python
   from pymilvus import connections, utility
   connections.connect(alias="default", host="127.0.0.1", port="19530")
   print(utility.get_collection_stats("hfusionhub_chunks"))
   ```
2. 源文件缺失 → 重新上传 `POST /api/document/upload`（multipart），再触发 `POST /api/vectorize/{id}` 重新解析/向量化。
3. 失效文档先软删 `DELETE /api/document/{id}`（进回收站可恢复），再 `purge`（物理删除，不可逆，会被权限校验拦截）。
4. 完整访问路径见 [ACCESS_MAP.md](ACCESS_MAP.md)。

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
cp ../java-backend/java-live.log java-backend.log

# Python 日志
cp ../python-ai/python-live.log python-ai.log

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

**最后更新**：2026-08-21  
**版本**：v1.1  
**维护者**：HFusionHub Team
