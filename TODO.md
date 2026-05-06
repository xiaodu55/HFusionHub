# 您需要完成的操作清单

## ✅ 已自动完成的任务

1. ✅ **主题偏好 API 补全**
   - 创建 `ThemePreferenceUpdateDTO.java`
   - 添加 `PATCH /api/user/theme-preference` 接口
   - 实现 `UserService.updateThemePreference()` 方法
   - Java 后端编译通过

2. ✅ **文档完善**
   - 创建 `docs/PRODUCTION_CHECKLIST.md` - 生产环境检查清单
   - 创建 `docs/SWAGGER_UI.md` - API 文档访问指南
   - 创建 `docs/PERFORMANCE_BASELINE.md` - 性能基线测试指南
   - 创建 `docs/TROUBLESHOOTING.md` - 故障排查手册（P0-P3 分级）
   - 创建 `docs/SCALING.md` - 扩容与性能优化指南
   - 创建 `scripts/run-all-benchmarks.ps1` - 自动化性能测试脚本

---

## 🔧 需要您手动完成的操作

### P0 — 核心配置（上线必需，5-10 分钟）

#### 1. 配置 DeepSeek API Key ⭐⭐⭐

**当前状态**：占位符，聊天走 Ollama fallback  
**影响**：聊天速度慢、质量一般  
**操作**：

```bash
# 编辑文件
文件路径: D:\college\development\HFusionHub1\python-ai\.env

# 找到这一行
DEEPSEEK_API_KEY=your-deepseek-api-key-here

# 替换为真实 Key（从 https://platform.deepseek.com/ 获取）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# 保存后重启 Python 服务
cd D:\college\development\HFusionHub1\python-ai
.venv\Scripts\activate
python -m app.main
```

**验证**：
```powershell
# 测试聊天功能，响应时间应 < 3s
cd D:\college\development\HFusionHub1
.\scripts\smoke-test.ps1
```

---

#### 2. 修改默认密码（生产环境）

**当前密码**（开发环境可用，生产必须改）：

```bash
文件路径: D:\college\development\HFusionHub1\docker\.env

# 需要修改的行（生产环境上线前）
ADMIN_PASSWORD=***REMOVED-BY-REWRITE***              # 改为强密码
MYSQL_ROOT_PASSWORD=***REMOVED-BY-REWRITE***      # 改为强密码
MYSQL_PASSWORD=***REMOVED-BY-REWRITE***           # 改为强密码
REDIS_PASSWORD=***REMOVED-BY-REWRITE***           # 改为强密码
MINIO_ROOT_PASSWORD=***REMOVED-BY-REWRITE***      # 改为强密码
PYTHON_AI_INTERNAL_TOKEN=<32字符随机字符串>    # 改为新 token
```

**密码建议**：
- 长度 ≥ 16 字符
- 包含大小写字母、数字、特殊符号
- 使用密码生成器（如 `openssl rand -base64 24`）

**修改后重启所有服务**：
```bash
cd D:\college\development\HFusionHub1\docker
docker compose down
docker compose up -d
```

---

### P1 — 功能验证（可选，10-15 分钟）

#### 3. 运行完整冒烟测试

**验证所有功能可用**：

```powershell
cd D:\college\development\HFusionHub1
.\scripts\smoke-test.ps1
```

**预期结果**：
```
==== 结果: 40+ PASS / 0 FAIL ====
```

**如果失败**：参考 `docs/TROUBLESHOOTING.md` 故障排查

---

#### 4. 运行性能基线测试

**建立性能基线**（用于未来对比）：

```powershell
cd D:\college\development\HFusionHub1
.\scripts\run-all-benchmarks.ps1 > docs/baselines/baseline-$(Get-Date -Format 'yyyyMMdd').txt
```

**查看报告**：
```powershell
cat docs/baselines/baseline-20260819.txt
```

**关键指标**（参考目标）：
- Java API P95 < 100ms
- RAG 检索 P95 < 500ms
- 文档处理 < 12s

---

#### 5. 访问所有服务确认登录

**浏览器打开以下地址并登录**：

| 服务 | 地址 | 用户名 | 密码 |
|------|------|--------|------|
| 主应用 | http://localhost:3000 | `admin` | `***REMOVED-BY-REWRITE***` |
| Swagger API | http://localhost:8080/swagger-ui/index.html | - | - |
| MinIO 控制台 | http://localhost:9001 | `minioadmin` | `***REMOVED-BY-REWRITE***` |
| Attu（Milvus UI） | http://localhost:8000 | 无需登录 | - |

**验证清单**：
- [ ] 主应用登录成功，能看到仪表盘
- [ ] Swagger UI 能看到 42+ 个接口
- [ ] MinIO 能看到 `hfusionhub` 桶
- [ ] Attu 能看到 `document_chunks` 集合

---

### P2 — 生产环境准备（上线前，1-2 小时）

#### 6. 完成生产环境检查清单

**逐项检查**：

```bash
文件路径: D:\college\development\HFusionHub1\docs\PRODUCTION_CHECKLIST.md
```

**关键项**：
- [ ] 修改所有默认密码
- [ ] 配置 HTTPS + 域名
- [ ] 限制 CORS 白名单（移除 `*`）
- [ ] 关闭或限制 Swagger UI 访问
- [ ] 配置数据库备份策略
- [ ] 启用 Prometheus + Grafana 监控

---

#### 7. 配置 HTTPS（Nginx 反向代理）

**示例配置**：

```nginx
# /etc/nginx/sites-available/hfusionhub.conf
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
    }

    location /api {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_buffering off;  # SSE 支持
    }
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;  # 强制 HTTPS
}
```

**获取 SSL 证书**（Let's Encrypt）：
```bash
sudo certbot --nginx -d your-domain.com
```

---

#### 8. 启用监控与告警

**Prometheus + Grafana 部署**：

```bash
cd D:\college\development\HFusionHub1\deploy\monitoring
docker compose up -d
```

**访问**：
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001（默认 admin/admin）

**导入仪表板**：
```
文件路径: deploy/monitoring/grafana-dashboard.json
```

**配置告警**（Slack/邮件）：
```
文件路径: deploy/monitoring/alert-rules.yml
```

---

### P3 — 持续优化（可选，按需进行）

#### 9. 数据库备份配置

**每日自动备份（Cron）**：

```bash
# Linux/Mac: /etc/cron.d/mysql-backup
0 3 * * * docker exec hfusionhub-mysql mysqldump -uroot -p<密码> hfusionhub_db | gzip > /backups/hfusionhub_$(date +\%Y\%m\%d).sql.gz

# Windows: 任务计划程序
# 脚本路径: scripts\backup-mysql.ps1
```

**备份保留策略**：
- 每日备份：保留 7 天
- 每周备份：保留 4 周
- 每月备份：保留 12 个月

---

#### 10. JVM 调优（大流量场景）

**编辑启动脚本**：

```bash
文件路径: D:\college\development\HFusionHub1\java-backend\start.sh

# 修改 JVM 参数（根据服务器配置调整）
java -Xms4g -Xmx8g \
     -XX:+UseG1GC \
     -XX:MaxGCPauseMillis=200 \
     -jar hfusionhub-backend.jar
```

**参考**：`docs/SCALING.md` 第 2 章

---

## 📋 下一步推进建议

### 本周内完成（必需）

1. ✅ 配置 DeepSeek API Key（P0）
2. ✅ 运行完整冒烟测试（P1）
3. ✅ 访问所有服务验证登录（P1）

### 两周内完成（推荐）

4. ✅ 运行性能基线测试并保存报告
5. ✅ 完成生产环境检查清单（前 50%）
6. ✅ 配置数据库备份策略

### 上线前完成（必需）

7. ✅ 修改所有默认密码
8. ✅ 配置 HTTPS + 域名
9. ✅ 启用监控与告警
10. ✅ 完成生产环境检查清单（100%）

---

## 🆘 遇到问题？

### 快速参考文档

| 问题类型 | 文档路径 |
|---------|---------|
| 服务启动失败 | `docs/TROUBLESHOOTING.md` 第 1-4 节 |
| 功能异常 | `docs/TROUBLESHOOTING.md` 第 5-8 节 |
| 性能问题 | `docs/TROUBLESHOOTING.md` 第 9-11 节 + `docs/SCALING.md` |
| API 文档 | `docs/SWAGGER_UI.md` |
| 生产环境配置 | `docs/PRODUCTION_CHECKLIST.md` |
| 扩容需求 | `docs/SCALING.md` |

### 自助诊断命令

```powershell
# 检查所有服务状态
docker ps

# 查看服务日志
docker logs -f hfusionhub-mysql
docker logs -f hfusionhub-redis
docker logs -f hfusionhub-milvus

# 快速健康检查
cd D:\college\development\HFusionHub1
.\scripts\smoke-test.ps1 -Quick
```

---

## 📊 预期完成时间线

| 阶段 | 时间 | 里程碑 |
|------|------|--------|
| P0 核心配置 | 今天（10 分钟）| DeepSeek API 接通，聊天质量提升 |
| P1 功能验证 | 今天（15 分钟）| 冒烟测试通过，性能基线建立 |
| P2 生产准备 | 本周内（2 小时）| 安全加固，监控上线 |
| P3 持续优化 | 按需进行 | 性能调优，成本优化 |

---

**当前状态**：✅ 所有自动化任务已完成  
**下一步**：👆 请按照 P0 操作完成 DeepSeek API Key 配置  
**预计耗时**：5 分钟  
**完成后**：聊天功能将使用 DeepSeek API（更快、更准确）

---

**生成时间**：2026-08-19  
**文档版本**：v1.0  
**最后更新**：刚刚完成
