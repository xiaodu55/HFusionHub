# HFusionHub 生产部署核对清单

> 生产部署（`deploy/`）前的逐项核对清单。任何一项未满足都可能导致安全或功能缺陷。
> 依据：2026-08 全栈验证 + `docs/ENVIRONMENT.md` + `docs/PRODUCTION_OPS.md`。

## 0. 前置依赖

- [ ] Docker 24+ / Docker Compose v2
- [ ] 域名证书（HTTPS 入口，Nginx/Ingress）
- [ ] 生产 MySQL 8.0（独立实例，非开发卷）
- [ ] 可用的 DeepSeek API Key（**非占位符**——本项目 `_is_placeholder_key` 会拒绝 `your_*_key` 类占位值，聊天将静默回退 Ollama）

## 1. 密钥与配置（deploy/.env）

- [ ] `MYSQL_ROOT_PASSWORD` / `MYSQL_PASSWORD`：强随机，不与开发环境共用
- [ ] `ADMIN_PASSWORD`：首次启动初始化 admin（无该值则不创建）
- [ ] `PYTHON_AI_INTERNAL_TOKEN` 与 `CALLBACK_SECRET`：两段长随机值，**Java 与 Python 两端一致**
- [ ] `DEEPSEEK_API_KEY`：真实 key（占位符会被跳过，静默回退本地模型）
- [ ] `PLUGIN_RUNNER_TOKEN`：runner 令牌
- [ ] `MINIO_ROOT_USER/PASSWORD`：非默认值
- [ ] `LLM_ALLOW_MOCK=false`、`EMBEDDING_ALLOW_FALLBACK=false`（生产禁止随机向量降级）

## 2. Plugin Runner（插件沙箱）

- [ ] 生成 TLS 证书：`bash scripts/generate-runner-tls.sh deploy/runner-tls`
- [ ] `PLUGIN_RUNNER_DOCKER_HOST=tcp://<docker-engine>:2376` 指向**隔离的 Docker 引擎**
- [ ] 证书挂载进 runner 容器（`deploy/docker-compose.prod.yml` 已配置）
- [ ] `docker compose ps` 中 plugin-runner 为 **healthy**（连不上 Docker 会 503/unhealthy——**开发环境已知问题，生产必须验证**）

## 3. 数据库与迁移

- [ ] Flyway 迁移：启动时自动执行 V1–V56+；**新表必须带 `tenant_id` 列**（否则租户拦截器 SQL 报错，见 `scripts/static-checks.py`）
- [ ] 备份策略：MySQL 每日备份；Milvus 向量卷备份（`scripts/backup_milvus.sh`）
- [ ] 迁移前在 staging 验证 `mvn flyway:migrate`（CI `java` job 已覆盖）

## 4. 特性开关（feature_flag 表，生产建议值）

- [ ] `agent.enabled=1`（Agent 工作流）
- [ ] `agent.write_tools.enabled=1`（写笔记，配合 `approval.required_for_write=1` 强制审批）
- [ ] `agent.web_search.enabled=0`（默认关闭；启用需确认 WEB_SEARCH_PROVIDER/配额）
- [ ] `agent.multi_agent.enabled=0`（默认关闭，收益未验证）
- [ ] `rag.hybrid.enabled=1`、`rag.graph.enabled=0`、`rag.reranker.enabled=0`（按检索评测调优）

## 5. 服务健康验证（部署后）

- [ ] `docker compose -f deploy/docker-compose.prod.yml ps` 全部 healthy（含 java/python/frontend/milvus/etcd/mysql/redis/minio/plugin-runner/attu）
- [ ] Java `/api/actuator/health` 200（db/redis/ping UP）
- [ ] Python `/health` 与 `/ready` 200
- [ ] 前端 https://<domain>/ 可登录
- [ ] 跑 `scripts/smoke-test.ps1`（或 CI 冒烟）全绿
- [ ] 跑 `python-ai/scripts/eval_offline.py` 门禁通过
- [ ] 实测一条知识库问答（有来源引用）+ 一次"保存笔记"审批流

## 6. 安全基线

- [ ] CI gitleaks 通过（无硬编码密钥）
- [ ] 内部端点仅经 X-Internal-Token 访问（`/internal/**` 已从登录检查排除，但受 token 保护）
- [ ] 插件沙箱：cap_drop=ALL、pids_limit、no-new-privileges（Dockerfile 已内置）
- [ ] 日志不打印密钥/提示词（`docs/ENVIRONMENT.md` 审计项）
- [ ] CORS 白名单指向生产域名

## 7. 监控与告警（deploy/docker-compose.monitoring.yml）

- [ ] Prometheus 抓取 `/actuator/prometheus`（Java）与 Python 指标
- [ ] 告警规则：服务 down、error_rate、p95 延迟、用量成本超预算
- [ ] 日志汇聚（ELK/Loki）

## 8. 回滚

- [ ] 镜像版本固定（`HFUSIONHUB_TAG` 而非 latest）
- [ ] 数据库迁移前备份（Flyway 不支持降级）
- [ ] Helm：`helm list` 版本回滚路径确认

---
*配套脚本：`scripts/smoke-test.ps1`（全功能冒烟）、`scripts/static-checks.py`（租户列/token 静态校验）、`python-ai/scripts/eval_offline.py`（离线评测门禁）。*
