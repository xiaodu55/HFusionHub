"""Platform built-in plugin wheels loader.

平台内建插件（P2-3：bid_docx / bid_quote）以 wheel 形式部署到 Python AI 服务，
启动时加载进本地插件 registry，使 ToolRegistry 能把 agent 工具调用路由到
容器沙箱执行（runner_mode=container + image_digest 经 Java versions 端点校验）。

供应链完整性：每个 wheel 必须带同名 ``<wheel>.sha256`` sidecar（单行 hex digest）——
即 scripts/plugin-provision.sh 构建时计算并写入的 SHA-256，缺失/不匹配则拒绝加载。

与 Java 侧解耦：Java plugin 表（V73 种子）提供 tool-specs 可见性与 image_digest 服务，
本模块提供 Python 本地可执行性，二者共同构成「平台内建插件」上架。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 环境变量：平台内建 wheel 目录（逗号分隔多目录）。dev 指向 python-ai/plugins/dist，
# 生产由 compose 挂载包含 bid_docx/bid_quote wheel + .sha256 的只读目录。
ENV_WHEELS_DIR = "PLUGIN_BUILTIN_WHEELS_DIR"


def _plugin_id_from_wheel(filename: str) -> str | None:
    """从 wheel 文件名解析 plugin_id（<name>@<version>）。

    文件名形如 bid_docx-1.0.0-py3-none-any.whl（build_wheel.py 产物）。
    """
    base = filename[:-4] if filename.endswith(".whl") else filename
    for suffix in ("-py3-none-any", "-py2.py3-none-any", "-py3-none-any.whl"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if "-" not in base:
        return None
    name, version = base.rsplit("-", 1)
    if not name or not version:
        return None
    return f"{name}@{version}"


def _read_sidecar_sha256(wheel_path: Path) -> str | None:
    sidecar = wheel_path.with_suffix(wheel_path.suffix + ".sha256")
    try:
        digest = sidecar.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return digest if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest) else None


def load_builtin_wheels(wheels_dir: str | None = None) -> list[str]:
    """加载指定目录下的平台内建插件 wheel，返回成功加载的 plugin_id 列表。

    目录不存在/为空时返回空列表（幂等，不抛异常）。单个 wheel 加载失败仅告警，
    不阻断其他 wheel（平台内建插件加载应尽力而为，但绝不静默放行未校验 wheel）。
    """
    from app.core.plugin.registry import load_and_register_wheel

    if wheels_dir is None:
        wheels_dir = os.environ.get(ENV_WHEELS_DIR, "")
    dirs = [d.strip() for d in wheels_dir.split(",") if d.strip()]
    if not dirs:
        return []

    loaded: list[str] = []
    for raw_dir in dirs:
        root = Path(raw_dir)
        if not root.is_dir():
            logger.warning("平台内建插件目录不存在，跳过: %s", raw_dir)
            continue
        for wheel_path in sorted(root.glob("*.whl")):
            expected = _read_sidecar_sha256(wheel_path)
            plugin_id = _plugin_id_from_wheel(wheel_path.name)
            if not expected:
                logger.warning(
                    "跳过平台内建插件 %s：缺少/非法 %s.sha256 sidecar（供应链校验）",
                    wheel_path.name, wheel_path.name,
                )
                continue
            if not plugin_id:
                logger.warning("跳过平台内建插件 %s：无法解析 plugin_id", wheel_path.name)
                continue
            try:
                registered = load_and_register_wheel(
                    wheel_path=str(wheel_path),
                    plugin_id=plugin_id,
                    expected_hash=expected,
                )
                loaded.append(registered.plugin_id)
                logger.info("平台内建插件已加载: %s (%s)", registered.plugin_id, wheel_path.name)
            except Exception as exc:  # noqa: BLE001 — 单个失败不阻断启动
                logger.error("平台内建插件加载失败 %s: %s", wheel_path.name, exc)
    return loaded
