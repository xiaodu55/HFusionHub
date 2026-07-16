# 待办操作清单

> 面向部署/运维的操作清单，按优先级分组。敏感值（密码、token）一律从
> `docker/.env` / `deploy/.env` 读取，**不要在文档中明文硬编码**。

## ✅ 已自动完成（2026-08-19）

- ✅ **DeepSeek API Key 已配置** — `python-ai/.env` 已写入真实 key（`deepseek-v4-flash`），流式聊天实测通过
- ✅ **冒烟测试全绿** — `scripts/smoke-test.ps1` 48 PASS / 0 FAIL
- ✅ **演示数据导入/清空** — `POST /api/demo/import` / `POST /api/demo/clear`
- ✅ **CORS 配置化** — 内网穿透（cpolar 动态域名）下浏览器登录 403 已修复
- ✅ **公网访问** — 改用生产预览（vite preview + preview.proxy），打包产物 <4s 渲染
- ✅ **隧道 URL 查询** — `scripts/get-tunnel-url.ps1`
- ✅ **分析扩展包已部署实跑（2026-08-31）** — `docker-compose.analytics.yml` 13 容器全部就绪；离线链路（全量导入 178,945 行→DWD/DWS→质量门禁 14 条全绿→ADS 回写 MySQL）与实时链路（Flink CDC→Kafka→1min 窗口→analytics_realtime_metrics 12,879 行）均实测打通；12 条踩坑记录见 docs/BIGDATA_ARCHITECTURE.md §5.2.1

## 🔧 需手动完成

### P0 — 上线安全（生产环境必需）

0. **【紧急】恢复 CI 运行** — GitHub Actions 因「recent account payments have failed or your spending limit needs to be increased」全部 job 3 秒即失败（2026-08-29 确认，main 分支 CI/E2E 连续红）。**2026-08-29 已复查：仓库侧 workflow 配置（触发器/job 定义/static-checks）全部正常，失败纯属账户计费**。需账户所有者到 GitHub Settings → Billing & plans 处理账单或提高 Spending limit（免费账户可将 Actions 用量降到 0 以内，或等待下月额度重置）。在恢复前，PR 门禁（含 eval-offline 阻断）实际失效，合并需本地跑全量测试兜底：**`.\scripts\run-all-tests.ps1`（一键串起 static-checks（含 --flyway-doc-sync）→ Java mvn test → Python pytest → 前端 build+vitest → gitleaks 泄漏扫描（未安装自动 SKIP），2026-09-01 增补）**，或手动逐项：`python scripts/static-checks.py` → Java `mvn test` → Python `pytest -q tests` → 前端 `npm run build && npx vitest run`
1. **修改默认密码** — ✅ 2026-08-30 复查：本地 `docker/.env` 与 `deploy/.env` 的全部密码/令牌键已是强随机值（非占位符/弱默认），`scripts/rotate-secrets.sh --check` 可随时复核。✅ **2026-09-01 已完成跨环境分离轮换**：`ADMIN_PASSWORD` / `CALLBACK_SECRET` / `PYTHON_AI_INTERNAL_TOKEN` 此前 docker 与 deploy 两环境完全相同、`docker` 的 `MINIO_SECRET_KEY` 与 `MYSQL_PASSWORD` 复用，均已各自重新生成（`MINIO_SECRET_KEY` 改指 MinIO root 真实口令，修复了既有的凭据不匹配）。轮换在**下次栈重启后生效**（`docker compose down && docker compose up -d`），数据库密码属卷内状态未动、需按 PRODUCTION_OPS 手动 ALTER USER。如需再次轮换用 `scripts/rotate-secrets.sh` 生成新值并同步两侧 .env
2. **配置 HTTPS** — `deploy/nginx-https.conf.example` 已提供完整模板：替换域名与证书路径后部署 Nginx + Let's Encrypt（`certbot certonly --webroot`），强制 HTTP→HTTPS（模板含 301 跳转与 SSE `proxy_buffering off`）
3. **收紧 CORS** — ✅ 仓库侧就绪（2026-08-30）：后端默认 fail-closed（未配置白名单时仅同源，`allow-any-origin` 默认 false），`deploy/.env.example` 已含 `CORS_ALLOWED_ORIGINS` 键与说明；生产 `deploy/.env` 填入真实域名白名单（逗号分隔）即生效，**不要用 `*`**（后端 allowCredentials=true 会拒绝通配且属安全隐患）
4. **关闭/限制 Swagger UI** — ✅ `deploy/docker-compose.prod.yml` 已默认 `SPRINGDOC_API_DOCS_ENABLED=false` / `SPRINGDOC_SWAGGER_UI_ENABLED=false`；如需临时开启在 `deploy/.env` 显式设置
5. **启用数据库备份** — ✅ 新增 `scripts/backup-mysql.sh`（生产容器版：一致性 dump + gzip + 校验 + 按天清理），crontab 示例见脚本头注释；Milvus 快照用 `scripts/backup_milvus.sh`；恢复后务必做一次恢复演练（PRODUCTION_OPS.md 第 8 节）
6. **【已完成 2026-09-01】git 历史中的数据库备份泄漏清除** — `backups/mysql/hfusionhub_drill.sql.gz`（含 sys_user bcrypt 哈希与租户数据）曾随「备份恢复演练」提交（eaf7bf9）进入 git 历史，根因是 `.gitignore` 写的是 `backup/` 而目录为 `backups/`。已用 `git filter-repo` 重写全部 270 个提交、修复 gitignore、删除 5 条引用旧历史的 dependabot 分支并 force push main；重写前全量 bundle 备份在仓库外 `../HFusionHub1-pre-rewrite.bundle`。**后续注意事项**：① 远端不可达对象 GitHub 侧可能缓存一段时间，可联系 GitHub Support 请求立即 GC；② 轮换前检出过该仓库的克隆需重新克隆（旧对象仍在其中）；③ 备份内的用户密码哈希已暴露，建议触发一次全员密码重置（管理员密码已随 .env 轮换更新）

### P1 — 功能验证

6. **运行完整冒烟测试**
   ```powershell
   .\scripts\smoke-test.ps1
   ```
   预期：`==== 结果: 48 PASS / 0 FAIL ====`
7. **运行性能基线**
   ```powershell
   .\scripts\run-all-benchmarks.ps1 > baseline-$(Get-Date -Format 'yyyyMMdd').txt
   ```
   参考目标：Java API P95 < 100ms、RAG 检索 P95 < 500ms、文档处理 < 12s（详见 [docs/SCALING.md](docs/SCALING.md)）

### P2 — 生产准备

7a. **分析扩展包剩余人工项**（可选，毕设演示用）— Superset 首启初始化管理员 + 搭建 5 张看板（bigdata/superset/README.md）；标准档加开 ClickHouse（--profile analytics-full）；Grafana 验证 analytics 告警组触发
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
**当前状态**：✅ 所有自动化任务已完成（DeepSeek 已配置、冒烟 48 PASS / 0 FAIL）  
**剩余**：👆 P0（上线安全）按需执行
