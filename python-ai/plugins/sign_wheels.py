#!/usr/bin/env python3
"""Platform built-in plugin wheel signer (P2-3 supply chain).

对 plugins/dist 下的平台内建插件 wheel：
  1. 确保 platform Ed25519 密钥对存在（默认 deploy/plugin-signing/platform-ed25519.pem，
     私钥绝不入库——见 .gitignore）
  2. 读取 wheel 内的 hfusion_plugin.json（与 loader 的 _read_manifest_from_zip 同源），
     调 app.core.plugin.signature.sign_plugin 生成 <wheel>.sig
  3. 把平台公钥注册进信任策略（HFUSIONHUB_PLUGIN_TRUST_DIR 指向的 policy.json），
     使 python-ai 启动加载器（builtins.py → load_and_register_wheel）的强制签名校验通过

用法：python plugins/sign_wheels.py [plugin ...]   （默认 bid_docx bid_quote）
"""

from __future__ import annotations

import base64
import json
import os
import sys
import zipfile

PYTHON_AI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # python-ai/
REPO_ROOT = os.path.dirname(PYTHON_AI_ROOT)
PLUGINS_ROOT = os.path.join(PYTHON_AI_ROOT, "plugins")
DIST_DIR = os.path.join(PLUGINS_ROOT, "dist")

sys.path.insert(0, PYTHON_AI_ROOT)

from app.core.plugin.signature import (  # noqa: E402
    register_trusted_key,
    sign_plugin,
    verify_signature,
)

PUBLISHER_NAME = "HFusionHub Platform"


def _default_key_path() -> str:
    return os.environ.get(
        "HFUSIONHUB_PLUGIN_SIGNING_KEY",
        os.path.join(REPO_ROOT, "deploy", "plugin-signing", "platform-ed25519.pem"),
    )


def _ensure_keypair(private_key_path: str) -> None:
    """确保平台 Ed25519 签名密钥对存在；不存在则生成（私钥 PKCS8 PEM）。"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if os.path.isfile(private_key_path):
        return
    os.makedirs(os.path.dirname(private_key_path), exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(private_key_path, "wb") as f:
        f.write(pem)
    try:
        os.chmod(private_key_path, 0o600)
    except OSError:
        pass  # Windows 上尽力而为
    print(f"key: generated {private_key_path}")


def _public_key_b64(private_key_path: str) -> str:
    from cryptography.hazmat.primitives import serialization

    with open(private_key_path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _manifest_from_wheel(wheel_path: str) -> dict:
    """与 loader._read_manifest_from_zip 同源：只认 wheel 根的 hfusion_plugin.json。"""
    with zipfile.ZipFile(wheel_path) as zf:
        with zf.open("hfusion_plugin.json") as f:
            return json.loads(f.read().decode("utf-8"))


def _wheel_path_for(plugin: str) -> str:
    manifest_path = os.path.join(PLUGINS_ROOT, plugin, "hfusion_plugin.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    dist_name = manifest["name"].replace("-", "_").replace(".", "_")
    return os.path.join(DIST_DIR, f"{dist_name}-{manifest['version']}-py3-none-any.whl")


def main() -> int:
    plugins = sys.argv[1:] or ["bid_docx", "bid_quote"]
    key_path = _default_key_path()
    _ensure_keypair(key_path)
    pub_b64 = _public_key_b64(key_path)

    # 平台公钥注册进信任策略（幂等）——运行时侧由同一 HFUSIONHUB_PLUGIN_TRUST_DIR 读取
    register_trusted_key(PUBLISHER_NAME, pub_b64, url="https://hfusionhub.example.com")

    failed = False
    for plugin in plugins:
        wheel_path = _wheel_path_for(plugin)
        if not os.path.isfile(wheel_path):
            print(f"::error::wheel not found: {wheel_path} (先运行 build_wheel.py)", file=sys.stderr)
            failed = True
            continue
        manifest = _manifest_from_wheel(wheel_path)
        sig_path = sign_plugin(wheel_path, manifest, key_path)
        # 自检：与加载器同路径的校验（含信任列表）必须通过
        verify_signature(wheel_path, manifest)
        print(f"signed: {plugin} -> {sig_path} (verified against trust policy)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
