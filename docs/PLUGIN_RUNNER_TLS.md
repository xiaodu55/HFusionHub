# 插件运行器 TLS 配置指引

> 状态：**dev 默认已解锁**。`docker/docker-compose.yml` 已内置 **dind sidecar**（P2-3）：
> `docker compose -f docker/docker-compose.yml up -d` 即获得隔离 Docker Engine + TLS 证书卷，
> `plugin-runner` 连接 `tcp://dind:2376`，healthy = 沙箱可用。详见
> [docs/PLUGIN_BUILTINS.md](PLUGIN_BUILTINS.md)。
>
> 本文其余部分保留两条备选路径：staging-rehearsal 独立 dind、宿主 daemon 直接开 TLS。

## dev 默认路径（compose dind sidecar）

1. 生成 dind 布局证书（`server/` 给 dind，`client/` 给 runner）：

   ```bash
   bash scripts/generate-runner-tls.sh deploy/runner-tls            # 基础证书
   bash scripts/generate-runner-tls.sh deploy/runner-tls --dind-layout
   ```

2. `cd docker && docker compose up -d dind plugin-runner` → runner healthcheck
   `curl /health` 连上引擎后返回 200（`docker_connected: true`）。

## 备选路径 A：staging-rehearsal 独立 dind

`scripts/staging-rehearsal.sh` 用 `docker run --privileged`（同证书布局，只读挂载
`deploy/runner-tls/dind-certs`）启动 `hfusionhub-rehearsal-dind` 并把 runner 指向
`tcp://host.docker.internal:2376`。与 compose dind sidecar 同占 `127.0.0.1:2376`，勿同时运行。

## 备选路径 B：宿主 daemon 直接开 TLS（历史方案）

让 plugin-runner 直连宿主 Docker Desktop 的 TLS 监听——需要主机级操作（修改 daemon.json 并
重启 Docker Desktop，所有容器中断），现已不推荐；仅当无法使用 privileged dind 时考虑。

<details>
<summary>宿主 daemon TLS 配置（展开查看）</summary>

编辑 `%USERPROFILE%\.docker\daemon.json`（Docker Desktop → Settings → Docker Engine）：

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

⚠️ 修改后需 **Apply & Restart** Docker Desktop —— 所有容器（MySQL/Milvus/Redis 等）会中断，
重启后需重新 `cd docker && docker compose up -d`。

</details>

## 生产环境

`deploy/docker-compose.prod.yml` 与 Helm 已内置 runner TLS 路径：
- `PLUGIN_RUNNER_DOCKER_HOST=tcp://remote-docker:2376`
- TLS 证书由 `generate-runner-tls.sh` 生成并注入（secrets → `/certs/client`）
- CI `plugin-security.yml` 覆盖容器安全门禁

## runner 不可用的影响

| 功能 | 影响 |
|---|---|
| 插件安装 / 列表 / 审计 | 正常（不依赖 runner） |
| 插件**沙箱执行**（含平台内建 bid_docx/bid_quote） | ❌ 不可用（runner fail-closed 返回 503 语义） |
| 平台核心（聊天/RAG/Agent/审批/笔记/用量） | ✅ 不受影响 |
