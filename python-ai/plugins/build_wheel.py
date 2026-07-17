#!/usr/bin/env python3
"""Deterministic flat-wheel builder for HFusionHub platform built-in plugins.

Wheel 布局（plugin loader 要求）：
  - hfusion_plugin.json      在 wheel 根（_read_manifest_from_zip 只认 zip 根）
  - tools.py                 在 wheel 根（容器 run_tool.py 从 /opt/plugin/ 加载）
  - *.dist-info/METADATA|WHEEL|RECORD

用法：python plugins/build_wheel.py [plugin_dir ...]   （默认 plugins/bid_docx）
产物：plugins/dist/<name>-<version>-py3-none-any.whl
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # python-ai/
PLUGINS_ROOT = os.path.join(ROOT, "plugins")
DIST_DIR = os.path.join(PLUGINS_ROOT, "dist")

# 随 wheel 打进根目录的文件（除 hfusion_plugin.json 外的插件实现文件）
ROOT_FILES = ("tools.py",)
# 也原样拷进 dist-info（供审计）
META_FILES = ("README.md",)


def _read_manifest(plugin_dir: str) -> dict:
    path = os.path.join(plugin_dir, "hfusion_plugin.json")
    with open(path, encoding="utf-8") as f:
        manifest = json.load(f)
    return manifest


def build_wheel(plugin_dir: str) -> str:
    manifest = _read_manifest(plugin_dir)
    name = manifest["name"]
    version = manifest["version"]
    dist_name = name.replace("-", "_").replace(".", "_")

    os.makedirs(DIST_DIR, exist_ok=True)
    wheel_name = f"{dist_name}-{version}-py3-none-any.whl"
    wheel_path = os.path.join(DIST_DIR, wheel_name)

    files: list[tuple[str, bytes]] = []
    # 插件实现文件（wheel 根）
    for fname in ROOT_FILES:
        fpath = os.path.join(plugin_dir, fname)
        if os.path.isfile(fpath):
            with open(fpath, "rb") as f:
                files.append((fname, f.read()))
    # manifest（wheel 根）
    with open(os.path.join(plugin_dir, "hfusion_plugin.json"), "rb") as f:
        files.append(("hfusion_plugin.json", f.read()))

    # dist-info
    dist_info = f"{dist_name}-{version}.dist-info"
    summary = manifest.get("description", "").splitlines()[0] if manifest.get("description") else name
    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: {dist_name}\n"
        f"Version: {version}\n"
        f"Summary: {summary}\n"
        f"Requires-Python: >=3.10\n"
    )
    for extra in manifest.get("dependencies", []):
        if isinstance(extra, dict) and extra.get("package"):
            metadata += f"Requires-Dist: {extra['package']}\n"
    metadata += "\n"
    files.append((f"{dist_info}/METADATA", metadata.encode("utf-8")))

    wheel_meta = "Wheel-Version: 1.0\nGenerator: hfusionhub-plugin-build\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n"
    files.append((f"{dist_info}/WHEEL", wheel_meta.encode("utf-8")))

    # 审计副本（不计入 wheel 的 RECORD 校验路径外）
    for fname in META_FILES:
        fpath = os.path.join(plugin_dir, fname)
        if os.path.isfile(fpath):
            with open(fpath, "rb") as f:
                content = f.read()
            files.append((f"{dist_info}/{fname}", content))

    # RECORD（含 hash，按 wheel 规范）
    record_rows = []
    for rel, content in files:
        hasher = hashlib.sha256()
        hasher.update(content)
        digest = base64.urlsafe_b64encode(hasher.digest()).rstrip(b"=").decode("ascii")
        record_rows.append((rel, f"sha256={digest}", str(len(content))))
    record_path = f"{dist_info}/RECORD"
    record_rows.append((record_path, "", ""))
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerows(record_rows)
    files.append((record_path, buf.getvalue().encode("utf-8")))

    # 写 wheel
    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, content in sorted(files, key=lambda x: x[0]):
            zf.writestr(rel, content)

    # 旁路输出清单供签名/校验；同时写 <wheel>.sha256 sidecar——
    # Python 启动加载器（app/core/plugin/builtins.py）按此校验供应链完整性。
    digest = hashlib.sha256()
    with open(wheel_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    # <wheel>.sha256 sidecar——Python 启动加载器（app/core/plugin/builtins.py）按此校验
    sidecar = wheel_path + ".sha256"
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write(digest.hexdigest() + "\n")
    print(f"wheel: {wheel_path}")
    print(f"sha256: {digest.hexdigest()}")
    print(f"sidecar: {sidecar}")
    return wheel_path


def main() -> int:
    targets = sys.argv[1:] or ["bid_docx"]
    for name in targets:
        plugin_dir = os.path.join(PLUGINS_ROOT, name)
        if not os.path.isdir(plugin_dir):
            print(f"::error::no such plugin dir: {plugin_dir}", file=sys.stderr)
            return 2
        build_wheel(plugin_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
