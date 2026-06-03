# bid_docx — 标书 docx 导出插件（平台内建）

HFusionHub 招投标垂直化 P2-3 的平台内建容器插件：把已审批的标书分节草稿
（`bid_draft` sections）渲染为 `.docx` 投标文件。

## 组成

| 文件 | 作用 |
| :--- | :--- |
| `tools.py` | 插件实现，暴露 `bid_export_docx` 工具函数 |
| `hfusion_plugin.json` | manifest + tool_specs（`sandbox.runner.mode=container`） |
| `pyproject.toml` | wheel 打包配置 |

## 容器契约

镜像必须包含 `/opt/plugin/run_tool.py`（固定入口，从
`docker/plugin-runner/run_tool.py` 拷贝）+ 插件 `tools.py`，并安装 `python-docx`。
Runner 经 `PLUGIN_TOOL_NAME` / `PLUGIN_TOOL_INPUT` 环境变量传参，
工具函数以关键字参数调用，stdout 输出单个 JSON 对象。

## 本地构建与验证

```bash
# 1. 构建 wheel
cd python-ai/plugins/bid_docx && python -m build

# 2. 构建镜像进 dind（TLS 客户端证书）
DOCKER_HOST=tcp://127.0.0.1:2376 DOCKER_TLS_VERIFY=1 \
  DOCKER_CERT_PATH=deploy/runner-tls/dind-certs/client \
  docker build -t hfusionhub-plugin-bid-docx:1.0.0 -f Dockerfile ../../..

# 3. 端到端调用
#    经 Java PluginController 安装后，Python ToolRegistry 按
#    sandbox.runner.mode=container 路由到 plugin-runner /execute。
```

## 输出

`bid_export_docx` 返回 JSON：`{filename, size_bytes, chars, base64}`，
`base64` 为 docx 字节的 ASCII 编码，调用方负责落盘/下发。
