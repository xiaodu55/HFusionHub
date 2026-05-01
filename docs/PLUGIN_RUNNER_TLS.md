# 插件运行器 TLS 配置指引

> 状态：**环境阻塞项**。本地开发默认 `plugin-runner` 容器为 unhealthy，原因是
> 宿主 Docker daemon 未开启 TLS 监听（:2376），而 Plugin Runner 出于安全设计
> **只通过 TCP+TLS 连接远程 Docker**（绝不挂载 docker.sock）。
>
> 该问题不影响平台核心功能（聊天 / RAG / 知识库 / Agent / 审批 / 笔记全部正常），
> 仅影响**插件沙箱执行**。修复需要主机级操作（重启 Docker Desktop），因此未自动执行。

## 为什么 unhealthy

`docker/plugin-runner/app.py` 用 `docker.from_env()` 连接：
- `DOCKER_HOST=tcp://host.docker.internal:2376`
- TLS 证书目录 `/certs`（`plugin-runner-certs` 卷，默认空）

容器健康检查 `curl /health` → runner 连不上 Docker daemon → 返回 503。

## 修复步骤（Windows Docker Desktop）

### 1. 生成 TLS 证书

需要 `openssl`（Git for Windows 自带；或 WSL 里执行）：

```powershell
# Git Bash / WSL
bash scripts/generate-runner-tls.sh deploy/runner-tls
# 生成 ca.pem / cert.pem / key.pem / server-cert.pem / server-key.pem
```

### 2. 配置 Docker daemon 开启 TLS

编辑 `%USERPROFILE%\.docker\daemon.json`（Docker Desktop → Settings → Docker Engine 可编辑）：

```json
{
  "tls": true,
  "tlsverify": true,
  "tlscacert": "C:\\path\\to\\deploy\\runner-tls\\dind-certs\\server\\ca.pem",
  "tlscert": "C:\\path\\to\\deploy\\runner-tls\\dind-certs\\server\\cert.pem",
  "tlskey": "C:\\path\\to\\deploy\\runner-tls\\dind-certs\\server\\key.pem",
  "hosts": ["tcp://0.0.0.0:2376", "npipe:////./pipe/docker_engine"]
}
```

> ⚠️ 修改后需 **Apply & Restart** Docker Desktop —— 所有容器（MySQL/Milvus/Redis 等）会中断，
> 重启后需重新 `cd docker && docker compose up -d`。

### 3. 重启 Plugin Runner（挂载证书）

```powershell
cd docker
docker compose up -d plugin-runner   # 证书卷由 compose 挂载
docker compose ps plugin-runner      # 期望 healthy
Invoke-WebRequest http://localhost:9100/health   # 期望 {"status":"healthy","docker_connected":true}
```

### 4. 验证插件执行

在 Python AI 侧注册插件 → 调用插件工具 → 查看 `plugin_execution_metric` 有执行记录。

## 生产环境（无需此操作）

`deploy/docker-compose.prod.yml` 与 Helm 已内置 runner TLS 路径：
- `PLUGIN_RUNNER_DOCKER_HOST=tcp://remote-docker:2376`
- TLS 证书由 `generate-runner-tls.sh` 生成并注入
- CI `plugin-security.yml` 覆盖容器安全门禁

## 不修复的影响

| 功能 | 影响 |
|---|---|
| 插件安装 / 列表 / 审计 | 正常（不依赖 runner） |
| 插件**沙箱执行**（调用插件工具） | ❌ 不可用（runner 503） |
| 平台核心（聊天/RAG/Agent/审批/笔记/用量） | ✅ 不受影响 |
