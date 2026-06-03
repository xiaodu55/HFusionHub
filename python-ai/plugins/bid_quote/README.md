# bid_quote — 投标报价表导出插件（平台内建）

HFusionHub 招投标垂直化 P2-3 的平台内建容器插件：把投标报价明细（`bid_quote`
items）渲染为 `.xlsx` 报价表，内嵌评分点计算（复用 `bid_calc_scoring` 确定性逻辑，
插件自包含、不依赖应用 ToolRegistry）。

## 组成

| 文件 | 作用 |
| :--- | :--- |
| `tools.py` | 插件实现，暴露 `bid_export_quote` 工具函数 |
| `hfusion_plugin.json` | manifest + tool_specs（`sandbox.runner.mode=container`） |
| `pyproject.toml` | wheel 打包配置 |

## 容器契约

镜像必须包含 `/opt/plugin/run_tool.py`（固定入口，从
`docker/plugin-runner/run_tool.py` 拷贝）+ 插件 `tools.py`，并安装 `openpyxl`。
Runner 经 `PLUGIN_TOOL_NAME` / `PLUGIN_TOOL_INPUT` 环境变量传参，
工具函数以关键字参数调用，stdout 输出单个 JSON 对象。

## 输出

`bid_export_quote` 返回 JSON：

```json
{
  "filename": "<项目名>-报价表.xlsx",
  "size_bytes": 12345,
  "currency": "¥",
  "totals": {"subtotal": 1000.0, "tax_amount": 60.0, "grand_total": 1060.0},
  "lines": 3,
  "scoring": {"items": [...], "total_score": 90.0, "max_total": 100.0},
  "base64": "<xlsx 字节的 base64>"
}
```

`base64` 为 xlsx 字节的 ASCII 编码，调用方负责落盘/下发。
