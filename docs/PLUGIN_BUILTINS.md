# 平台内建插件（P2-3：bid_docx / bid_quote）

> 状态：**已落地**。两个平台内建插件经「wheel 构建 → 平台签名 → 镜像构建 → dind 载入 →
> image_digest 回填」管线完成上架，dev 沙箱由 compose dind sidecar 解锁，e2e 验收
> `scripts/plugin-builtins-e2e.ps1` 全绿（17 项）。

## 内建插件一览

| plugin_id | 工具 | 输出 | 复用逻辑 |
|---|---|---|---|
| `bid_docx@1.0.0` | `bid_export_docx` | `.docx`（base64 + 元信息） | 标书分节草稿渲染 |
| `bid_quote@1.0.0` | `bid_export_quote` | `.xlsx`（base64 + totals/scoring） | `bid_calc_scoring` 确定性评分计算 |

源码：`python-ai/plugins/<name>/`（`tools.py` + `hfusion_plugin.json` manifest + `pyproject.toml`）。
manifest 与 tool_specs 同步注册在 Java `plugin` 表（`V73__bid_plugin_builtins.sql`，`tenant_id IS NULL` = 平台内建）。

## 三方协作模型

| 组件 | 职责 |
|---|---|
| Java `plugin` 表（V73 种子） | 插件目录可见性（tool-specs 上报给 agent）+ `container_image` / `image_digest` 供应链锚点 |
| Python `app/core/plugin/builtins.py` | 启动时从 `PLUGIN_BUILTIN_WHEELS_DIR` 加载 wheel 进本地 registry（`.sha256` sidecar + Ed25519 签名双重校验），使 ToolRegistry 可路由到容器沙箱 |
| plugin-runner + dind | 容器沙箱执行：`/execute` 按常量时间比较校验 `image_digest`，网络策略 + 只读 rootfs + 资源限制 |

## provision 管线（scripts/plugin-provision.sh）

```bash
bash scripts/plugin-provision.sh          # dev：构建 + 签名 + 载入 dind + 回填 digest
HUB_DOCKER_REGISTRY=reg.example.com/hf bash scripts/plugin-provision.sh   # prod：推送 registry
```

1. **构建 wheel**：`python-ai/plugins/build_wheel.py` → `dist/<name>-<version>-py3-none-any.whl` + `.sha256` sidecar
2. **平台签名**：`python-ai/plugins/sign_wheels.py`
   - 确保 platform Ed25519 密钥对（`deploy/plugin-signing/platform-ed25519.pem`，**私钥绝不入库**，首次运行生成）
   - 生成 `<wheel>.sig` 签名束（manifest_hash + artifact_hash 绑定）
   - 平台公钥注册进信任策略 `HFUSIONHUB_PLUGIN_TRUST_DIR/policy.json`（dev 默认 `python-ai/plugins/trust/`，gitignored）
3. **构建镜像**：`docker/Dockerfile.plugin-<name>`（`python:3.12-slim` + 依赖 + `run_tool.py` 固定入口 + `tools.py`）
4. **载入 dind**（dev）：`docker save | dind docker load`；prod：tag + push registry
5. **回填 digest**：本地构建取 config digest（`{{.Id}}`，runner 对未推送镜像的回退锚点）/ registry 取 RepoDigest，经 mysql 容器 `UPDATE plugin ... WHERE tenant_id IS NULL`

## dev 沙箱解锁（docker/docker-compose.yml）

- **dind sidecar**：`dind` 服务（`docker:27-dind`，privileged，只读挂载 `deploy/runner-tls/dind-certs/`，
  证书由 `bash scripts/generate-runner-tls.sh deploy/runner-tls --dind-layout` 预生成；`dind-data` 卷持久化镜像）
- **plugin-runner**：`DOCKER_HOST=tcp://dind:2376`（可用 `PLUGIN_RUNNER_DOCKER_HOST` 覆盖为外部隔离引擎），
  客户端证书挂载 `dind-certs/client:/certs/client:ro`；healthcheck 仅在连上引擎时 2xx → runner healthy = 沙箱已解锁
- **python-ai**：`PLUGIN_BUILTIN_WHEELS_DIR=/plugin-wheels`（挂载 `python-ai/plugins/dist`）+
  `HFUSIONHUB_PLUGIN_TRUST_DIR=/plugin-trust`（挂载 `python-ai/plugins/trust`）
- 本机进程开发：`scripts/restart-modules.ps1 -Modules python` 自动注入上述两个目录变量

> 与 `staging-rehearsal.sh` 的独立 dind（`hfusionhub-rehearsal-dind`）同占 `127.0.0.1:2376`，勿同时运行。

## 租户可见性

`plugin` 表已加入 `MybatisPlusConfig.TENANT_IGNORE_TABLES`（与 `bid_template`/`bid_subscription` 同模式：
`tenant_id` 可空 = 平台级行），可见性由服务层过滤（`PluginServiceImpl#visibleToTenant`）：

- 平台内建插件（`tenant_id IS NULL`）→ **所有租户可见**
- 租户自有插件 → 仅所属租户可见；跨租户访问按「不存在」处理
- 系统作用域（管理后台）→ 全量可见

## e2e 验收

```powershell
.\scripts\plugin-builtins-e2e.ps1 -RunnerContainer plugin-runner
```

17 项断言：镜像在 dind 就绪、bid_docx 真实渲染 `.docx`（ZIP 魔数）、bid_quote 报价数学
（subtotal/tax/grand_total）与评分汇总（total/weighted）、错误 digest 拒绝、缺失 digest 拒绝。

## 与 MCP 第三方工具的关系

两条**相互独立**的扩展路径，互不影响：

| | 平台内建插件 | MCP 第三方工具 |
|---|---|---|
| 注册 | `plugin` 表 + wheel 加载 | `McpClientManager`（`MCP_SERVERS_CONFIG_FILE`，启动 best-effort） |
| 执行 | ToolRegistry → `execute_plugin_tool` → runner 容器沙箱（digest 校验） | ToolRegistry（`_mcp_server_id` 路由）→ `manager.call_tool` → 远端 MCP server |
| 治理 | 插件沙箱策略 + image_digest 供应链 | `risk_level=EXTERNAL` 策略引擎（只读模式拒绝/审批） |

HFusionHub 自身作为 MCP server 暴露工具（`/mcp/tools`，json-rpc-2.0）不受本节改动影响。
