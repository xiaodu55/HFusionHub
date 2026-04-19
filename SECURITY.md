# Security Policy

HFusionHub 关注安全问题。如果你发现任何安全漏洞，请按照以下流程报告，
而不要公开发布 Issue。

## 支持的版本

| 版本 | 支持状态 |
|------|----------|
| 1.0.x | ✅ 支持（当前稳定版） |
| < 1.0 | ❌ 不再支持 |

## 报告安全漏洞

请**不要**在 GitHub Issues 中公开安全漏洞。请通过以下任一渠道私下报告：

1. **GitHub 私有安全公告**：打开仓库的
   [Security → Advisories](https://github.com/xiaodu55/HFusionHub1/security/advisories)
   页面，点击 "New draft security advisory" 创建私有报告（推荐）。
2. **邮件**：发送邮件到项目维护者（邮件地址见仓库主页简介）。

请在报告中包含以下信息，以便快速定位与修复：

- 漏洞类型（如 RCE、SQL 注入、XSS、越权、密钥泄露等）
- 影响的服务与端点（Java Backend / Python AI / Frontend / Plugin Runner）
- 复现步骤（含最小复现请求/输入）
- 影响范围与可能造成的后果
- （可选）建议的修复方案

## 响应承诺

- **24 小时内**：确认收到报告，开始评估。
- **72 小时内**：给出初步评估结论与修复计划。
- **修复完成后**：在修复发布前，我们会与你同步确认；发布后公开致谢
  （若你同意公开身份）。

## 安全设计基线

- **最小权限**：Python AI 仅通过 `X-Internal-Token` 接受 Java 内部调用；
  plugin-runner 只连接隔离 Docker Engine（TLS），绝不挂载 `/var/run/docker.sock`。
- **密钥管理**：所有密码/令牌通过环境变量注入，`.env` 文件不入库；
  生产部署必须使用强随机值（见 `scripts/init-env.ps1` / `init-env.sh`）。
- **传输安全**：生产环境建议强制 HTTPS（Ingress / Nginx TLS）。
- **依赖安全**：CI 执行 `npm audit`、gitleaks 密钥扫描、pip 依赖审计。

## 更新密钥

如果怀疑密钥已泄露（例如本机 `python-ai/.env` 中的 API Key），请立即：
1. 在供应商控制台轮换该 Key；
2. 运行 `scripts/init-env.ps1`（或 `init-env.sh`）重新生成全部随机口令；
3. 重启相关服务。
