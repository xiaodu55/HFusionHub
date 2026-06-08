# 待办操作清单

> 面向部署/运维的操作清单，按优先级分组。敏感值（密码、token）一律从
> `docker/.env` / `deploy/.env` 读取，**不要在文档中明文硬编码**。

## ✅ 已自动完成（2026-08-19）

- ✅ **DeepSeek API Key 已配置** — `python-ai/.env` 已写入真实 key（`deepseek-v4-flash`），流式聊天实测通过
- ✅ **冒烟测试全绿** — `scripts/smoke-test.ps1` 47 PASS / 0 FAIL
- ✅ **演示数据导入/清空** — `POST /api/demo/import` / `POST /api/demo/clear`
- ✅ **CORS 配置化** — 内网穿透（cpolar 动态域名）下浏览器登录 403 已修复
- ✅ **公网访问** — 改用生产预览（vite preview + preview.proxy），打包产物 <4s 渲染
- ✅ **隧道 URL 查询** — `scripts/get-tunnel-url.ps1`

## 🔧 需手动完成

### P0 — 上线安全（生产环境必需）

1. **修改默认密码** — `docker/.env` 中 `ADMIN_PASSWORD` / `MYSQL_ROOT_PASSWORD` / `MYSQL_PASSWORD` / `REDIS_PASSWORD` / `MINIO_ROOT_PASSWORD` 替换为强随机值（可用 `openssl rand -base64 24` 或 `scripts/init-env.ps1` 重新生成），修改后 `docker compose down && docker compose up -d`
2. **配置 HTTPS** — 按 [docs/PRODUCTION_OPS.md](docs/PRODUCTION_OPS.md) 第 0 节配置 Nginx + Let's Encrypt，强制 HTTP→HTTPS
3. **收紧 CORS** — `CORS_ALLOWED_ORIGINS` 移除 `*`，仅保留真实域名
4. **关闭/限制 Swagger UI** — 生产 `springdoc.swagger-ui.enabled=false` 或 IP 白名单（见 [docs/SWAGGER_UI.md](docs/SWAGGER_UI.md)）
5. **启用数据库备份** — MySQL 每日 mysqldump + Milvus 卷快照（见 [docs/PRODUCTION_OPS.md](docs/PRODUCTION_OPS.md) 第 8 节容灾）

### P1 — 功能验证

6. **运行完整冒烟测试**
   ```powershell
   .\scripts\smoke-test.ps1
   ```
   预期：`==== 结果: 47 PASS / 0 FAIL ====`
7. **运行性能基线**
   ```powershell
   .\scripts\run-all-benchmarks.ps1 > baseline-$(Get-Date -Format 'yyyyMMdd').txt
   ```
   参考目标：Java API P95 < 100ms、RAG 检索 P95 < 500ms、文档处理 < 12s（详见 [docs/SCALING.md](docs/SCALING.md)）

### P2 — 生产准备

8. **逐项核对生产检查清单** — [docs/PRODUCTION_OPS.md](docs/PRODUCTION_OPS.md) 第 0 节（安全/持久化/性能/监控/合规）
9. **启用监控告警** — `deploy/monitoring/`（Prometheus + Grafana + 告警规则）
10. **配置 Plugin Runner TLS** — 按 [docs/PLUGIN_RUNNER_TLS.md](docs/PLUGIN_RUNNER_TLS.md) 生成证书并挂载（dev compose dind sidecar 下 healthy（引擎不可用时 503 属 fail-closed 设计））

### P3 — 持续优化

11. **JVM 调优** — 参考 [docs/SCALING.md](docs/SCALING.md) 垂直扩容节（`-Xms4g -Xmx8g -XX:+UseG1GC`）
12. **eval-nightly 启用** — GitHub 配置 `vars.EVAL_BASE_URL` + `secrets.EVAL_INTERNAL_TOKEN`

---

## 🆘 遇到问题？

| 问题类型 | 参考 |
|---------|------|
| 启动/重启/排障 | [docs/startup-guide.md](docs/startup-guide.md) |
| 故障排查 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 性能/扩容 | [docs/SCALING.md](docs/SCALING.md) |
| 生产运维 | [docs/PRODUCTION_OPS.md](docs/PRODUCTION_OPS.md) |
| API 文档 | [docs/SWAGGER_UI.md](docs/SWAGGER_UI.md) |

---

**生成时间**：2026-08-19  
**当前状态**：✅ 所有自动化任务已完成（DeepSeek 已配置、冒烟 47 PASS / 0 FAIL）  
**剩余**：👆 P0（上线安全）按需执行
