# FAQ（常见问题）

> 高频问题速查。排障手册见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)，配置项全集见 [ENVIRONMENT.md](ENVIRONMENT.md)。

## 功能与菜单

### 为什么「运行记录 / 待确认操作 / 我的笔记 / 我的记忆」是空的？
这些页面依赖 AI 能力（Agent/工具审批/写笔记/自动记忆），对应能力开关
`agent.enabled` **默认关闭**（管理 → 能力开关中开启）。手动创建的笔记/记忆不受影响。

### 「插件管理」报错 / 不可用？
插件执行依赖 plugin-runner 服务（需要 `PLUGIN_RUNNER_TOKEN`，且生产建议独立
TLS Docker Engine）。未部署 runner 时页面按 fail-closed 显示错误——这是预期行为，
不是故障。见 [docs/PLUGIN_RUNNER_TLS.md](PLUGIN_RUNNER_TLS.md)。

### 「套餐中心」的"导入行业演示数据"按钮点了没反应？
演示数据端点 `/demo/*` 生产默认关闭（`/demo/clear` 有数据破坏性）。开发 compose
默认开启；生产需在 `deploy/.env` 显式设置 `DEMO_ENDPOINTS_ENABLED=true`。

### 忘记密码怎么办？
项目未接入邮件服务，无法自助邮件找回。请联系管理员在「账号权限」页为你的账号
重置密码（管理员重置无需旧密码；管理员自己走「修改密码」）。

### 检索是几路召回？
两路：向量语义 + 关键词（BM25）混合（P5）。GraphRAG 已移除；cross_encoder 重排
可选开启（`RAG_RERANKER_MODE`）。

## 部署与运维

### GitHub Actions 全部失败？
检查账户 Billing / Spending limit（job 3 秒即失败属计费拦截，非代码问题）。

### Grafana 打不开 / 端口冲突？
监控栈 Grafana 绑定 `127.0.0.1:3001`（3000 留给前端 dev server）。

### 数据库如何备份恢复？
`scripts/backup-mysql.sh`（一致性 dump + 校验 + 按天清理）+ `scripts/backup_milvus.sh`
（向量快照）。恢复流程见 [PRODUCTION_OPS.md](PRODUCTION_OPS.md) 第 8 节，务必先演练。
