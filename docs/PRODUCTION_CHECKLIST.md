# 生产环境检查清单

## 🔐 安全配置

### 必需项（上线前必须完成）

- [ ] **修改所有默认密码**
  - `docker/.env` → `ADMIN_PASSWORD`（当前：`***REMOVED-BY-REWRITE***`）
  - `docker/.env` → `MYSQL_ROOT_PASSWORD`（当前：`***REMOVED-BY-REWRITE***`）
  - `docker/.env` → `MYSQL_PASSWORD`（当前：`***REMOVED-BY-REWRITE***`）
  - `docker/.env` → `REDIS_PASSWORD`（当前：`***REMOVED-BY-REWRITE***`）
  - `docker/.env` → `MINIO_ROOT_PASSWORD`（当前：`***REMOVED-BY-REWRITE***`）

- [ ] **配置真实 DeepSeek API Key**
  - `python-ai/.env` → `DEEPSEEK_API_KEY=sk-your-real-key`
  - 当前为占位符，聊天默认走 Ollama fallback

- [ ] **更新内部通信令牌**
  - `docker/.env` → `PYTHON_AI_INTERNAL_TOKEN`（32 字符随机字符串）
  - `docker/.env` → `PLUGIN_RUNNER_SECRET_KEY`（32 字符随机字符串）

- [ ] **启用 HTTPS**
  - 配置 Nginx 反向代理（示例：`deploy/nginx.conf`）
  - 申请 SSL 证书（Let's Encrypt 推荐）
  - 强制 HTTP → HTTPS 重定向

- [ ] **CORS 白名单**
  - `docker/.env` → `CORS_ALLOWED_ORIGINS=https://your-domain.com`
  - 移除 `*` 通配符

- [ ] **Sa-Token JWT 密钥**
  - `docker/.env` → `SA_TOKEN_JWT_SECRET_KEY`（建议 64 字符）

---

## 🗄️ 数据库与持久化

- [ ] **Flyway 迁移验证**
  - 确保 V1–V57 全部成功应用
  - 检查 `flyway_schema_history` 表状态

- [ ] **备份策略**
  - MySQL 每日备份（推荐 3AM cron + mysqldump）
  - Milvus 数据卷定期快照
  - MinIO 文件桶备份（mc mirror）

- [ ] **Redis 持久化**
  - AOF 已启用（`appendonly yes`）
  - RDB 每小时备份（`save 3600 1`）

---

## 🚀 性能与扩展性

- [ ] **资源限制**
  - Docker Compose `deploy.resources.limits` 已配置
  - JVM 堆内存：`-Xmx4g -Xms2g`（根据实际调整）
  - Python worker 数：`WEB_CONCURRENCY=4`

- [ ] **连接池优化**
  - HikariCP `maximum-pool-size=20`（根据负载调整）
  - Milvus 连接池：`MILVUS_POOL_SIZE=10`

- [ ] **向量索引参数**
  - Milvus HNSW `M=16, efConstruction=200`（默认值，超 100 万条数据需调优）

- [ ] **缓存预热**
  - 高频知识库元数据预加载
  - Prompt 模板缓存

---

## 📊 监控与告警

- [ ] **Prometheus + Grafana**
  - 导入 `deploy/monitoring/grafana-dashboard.json`
  - 配置告警规则（CPU > 80%、内存 > 90%、磁盘 > 85%）

- [ ] **关键指标监控**
  - 文档解析成功率（目标 > 95%）
  - RAG 检索 P95 延迟（目标 < 500ms）
  - Agent 任务超时率（目标 < 5%）
  - 用量配额告警（> 90%）

- [ ] **日志聚合**
  - ELK Stack 或 Loki + Grafana
  - 关键错误日志告警（Slack/邮件/钉钉）

- [ ] **健康检查**
  - Java：`GET /actuator/health`
  - Python：`GET /health`
  - 配置 Docker healthcheck 或 K8s liveness/readiness

---

## 🧪 测试验证

- [ ] **冒烟测试通过**
  ```powershell
  .\scripts\smoke-test.ps1
  ```
  全部项目 PASS（Java API + Python AI + 核心链路）

- [ ] **E2E 测试通过**
  ```bash
  cd hfusionhub-frontend && npx playwright test
  ```
  所有场景通过（登录、文档上传、聊天、主题切换、配额展示）

- [ ] **压力测试**
  - 并发用户：100（JMeter/Locust）
  - 文档上传→解析→检索链路稳定性
  - 数据库连接池无泄漏

---

## 🔧 运维工具

- [ ] **备份恢复演练**
  - 模拟 MySQL 数据丢失 → 从备份恢复 → 验证数据完整性
  - 模拟 Milvus 数据损坏 → 重建向量索引

- [ ] **日志轮转**
  - Docker 日志：`max-size: 100m, max-file: 3`
  - 应用日志：Logback 每日切分（保留 30 天）

- [ ] **灾难恢复计划**
  - RTO（恢复时间目标）：< 4 小时
  - RPO（恢复点目标）：< 24 小时

---

## 📜 合规与文档

- [ ] **隐私政策**
  - 用户数据处理声明
  - Cookie 使用说明

- [ ] **API 文档**
  - Swagger UI：`http://localhost:8080/swagger-ui/index.html`
  - 确保生产环境关闭或限制访问（`springdoc.swagger-ui.enabled=false`）

- [ ] **运维文档**
  - 故障排查手册（`docs/TROUBLESHOOTING.md`）
  - 扩容步骤（`docs/SCALING.md`）

---

## ✅ 上线前最终确认

- [ ] 所有必需项（🔐 安全配置）已完成
- [ ] 在预生产环境运行 7 天无 P0/P1 故障
- [ ] 备份恢复流程已演练
- [ ] 监控告警已配置并测试
- [ ] 回滚计划已准备（Docker 镜像版本标记）

---

## 📞 应急联系人

| 角色 | 姓名 | 联系方式 | 职责 |
|------|------|----------|------|
| 技术负责人 | ___ | ___ | 架构决策、P0 故障 |
| 后端开发 | ___ | ___ | Java/Python 服务 |
| 运维工程师 | ___ | ___ | 基础设施、监控 |
| DBA | ___ | ___ | 数据库优化、备份 |

---

**生成日期**：2026-08-19  
**文档版本**：v1.0  
**下次审查**：每季度或重大版本发布前
