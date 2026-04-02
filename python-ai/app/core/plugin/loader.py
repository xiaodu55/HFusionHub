"""Plugin loader — manifest validation + archive integrity (NO code execution).

This module ONLY:
  1. Reads and validates the manifest from a wheel/zip
  2. Computes SHA-256 hashes of manifest and archive
  3. Extracts the archive to a temp directory
  4. Discovers tool spec declarations (JSON only, no code execution)

Plugin CODE is NEVER executed in the main process.  Execution happens
exclusively in sandboxed subprocesses via `sandbox_runner.py`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .manifest import (
    ManifestError,
    compute_manifest_hash,
    validate_manifest,
)

# Signature verification (optional dependency — graceful fallback)
try:
    from .signature import verify_signature, SignatureError, UntrustedPublisherError, RevokedKeyError
    _HAS_SIGNATURE = True
except ImportError:
    _HAS_SIGNATURE = False

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "hfusion_plugin.json"
MAX_ARCHIVE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_MANIFEST_SIZE_BYTES = 64 * 1024  # 64 KB


@dataclass(frozen=True)
class PluginDescriptor:
    """Metadata about a loaded plugin — contains NO executable module reference."""
    plugin_id: str
    name: str
    version: str
    manifest: Dict[str, Any]
    manifest_hash: str
    archive_path: str
    archive_hash: str
    extract_dir: str  # Where the wheel was extracted (used by sandbox runner)
    tool_specs: List[Dict[str, Any]] = field(default_factory=list)
    sandbox_config: Optional[Dict[str, Any]] = None


class PluginLoadError(Exception):
    def __init__(self, plugin_name: str, reason: str):
        self.plugin_name = plugin_name
        self.reason = reason
        super().__init__(f"插件加载失败 '{plugin_name}': {reason}")


def load_plugin_from_wheel(
    wheel_path: str,
    plugin_id: Optional[str] = None,
    require_hash: bool = True,
    expected_hash: Optional[str] = None,
    verify_sig: bool = True,
) -> PluginDescriptor:
    """Load plugin metadata from a wheel.  Does NOT execute any plugin code.

    Steps:
      1. Validate archive exists and size
      2. Read and validate manifest JSON
      3. Compute SHA-256 hashes
      4. Verify signature against trusted publishers
      5. Extract archive to temp dir
      6. Parse tool specs from JSON files (no Python import)
      7. Return descriptor with extract_dir for sandboxed execution
    """
    wheel_path = os.path.abspath(wheel_path)
    if not os.path.isfile(wheel_path):
        raise PluginLoadError("(unknown)", f"文件不存在: {wheel_path}")

    file_size = os.path.getsize(wheel_path)
    if file_size > MAX_ARCHIVE_SIZE_BYTES:
        raise PluginLoadError("(unknown)", f"插件包过大: {file_size} bytes (最大 {MAX_ARCHIVE_SIZE_BYTES})")

    if not zipfile.is_zipfile(wheel_path):
        raise PluginLoadError("(unknown)", f"不是有效的 zip/wheel 文件: {wheel_path}")

    # 1. Read manifest
    manifest = _read_manifest_from_zip(wheel_path)
    name = manifest["name"]

    # 2. Validate manifest
    try:
        validate_manifest(manifest)
    except ManifestError as e:
        raise PluginLoadError(name, str(e))

    # 3. Compute hashes
    manifest_hash = compute_manifest_hash(manifest)
    archive_hash = _compute_archive_hash(wheel_path)

    # 4. Mandatory hash verification
    if require_hash and not expected_hash:
        raise PluginLoadError(name, "安装需要提供 expected_hash（供应链完整性校验）")
    if expected_hash and archive_hash != expected_hash:
        raise PluginLoadError(
            name,
            f"归档完整性校验失败: expected={expected_hash[:16]}... got={archive_hash[:16]}..."
        )

    # 5. Signature verification (supply chain integrity)
    if verify_sig:
        if not _HAS_SIGNATURE:
            raise PluginLoadError(
                name,
                "签名验证不可用（缺少 cryptography 依赖），"
                "无法完成供应链完整性校验。请安装 cryptography: pip install cryptography>=42.0.0"
            )
        try:
            verify_signature(wheel_path, manifest)
        except (SignatureError, UntrustedPublisherError, RevokedKeyError) as e:
            raise PluginLoadError(name, f"签名验证失败: {e}")

    # 6. Extract (no code execution)
    extract_dir = _extract_wheel(wheel_path, name)

    # 7. Parse tool specs from JSON files only (no Python import)
    tool_specs = _parse_tool_specs_from_extracted(extract_dir, manifest)

    sandbox_config = manifest.get("sandbox")

    pid = plugin_id or f"{name}@{manifest['version']}"
    logger.info("插件元数据加载成功: %s (hash=%s...)", pid, manifest_hash[:16])

    return PluginDescriptor(
        plugin_id=pid,
        name=name,
        version=manifest["version"],
        manifest=manifest,
        manifest_hash=manifest_hash,
        archive_path=wheel_path,
        archive_hash=archive_hash,
        extract_dir=extract_dir,
        tool_specs=tool_specs,
        sandbox_config=sandbox_config,
    )


def load_plugin_from_directory(
    dir_path: str,
    plugin_id: Optional[str] = None,
) -> PluginDescriptor:
    """Load plugin metadata from a directory.  Does NOT execute any plugin code."""
    dir_path = os.path.abspath(dir_path)
    if not os.path.isdir(dir_path):
        raise PluginLoadError("(unknown)", f"目录不存在: {dir_path}")

    manifest_path = os.path.join(dir_path, MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
        raise PluginLoadError("(unknown)", f"目录中未找到 {MANIFEST_FILENAME}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    name = manifest.get("name", "unknown")

    try:
        validate_manifest(manifest)
    except ManifestError as e:
        raise PluginLoadError(name, str(e))

    manifest_hash = compute_manifest_hash(manifest)
    archive_hash = _compute_directory_hash(dir_path)
    tool_specs = _parse_tool_specs_from_extracted(dir_path, manifest)
    sandbox_config = manifest.get("sandbox")

    pid = plugin_id or f"{name}@{manifest.get('version', '0.0.0')}"
    logger.info("插件从目录加载（元数据）: %s", pid)

    return PluginDescriptor(
        plugin_id=pid,
        name=name,
        version=manifest.get("version", "0.0.0"),
        manifest=manifest,
        manifest_hash=manifest_hash,
        archive_path=dir_path,
        archive_hash=archive_hash,
        extract_dir=dir_path,
        tool_specs=tool_specs,
        sandbox_config=sandbox_config,
    )


# ── Internal helpers ─────────────────────────────────────────────────

def _read_manifest_from_zip(zip_path: str) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if MANIFEST_FILENAME not in zf.namelist():
                raise PluginLoadError("(unknown)", f"zip 中未找到 {MANIFEST_FILENAME}")
            info = zf.getinfo(MANIFEST_FILENAME)
            if info.file_size > MAX_MANIFEST_SIZE_BYTES:
                raise PluginLoadError("(unknown)", f"manifest 过大: {info.file_size} bytes")
            raw = zf.read(MANIFEST_FILENAME).decode("utf-8")
            return json.loads(raw)
    except zipfile.BadZipFile as e:
        raise PluginLoadError("(unknown)", f"无效的 zip 文件: {e}")


def _compute_archive_hash(archive_path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(archive_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _compute_directory_hash(dir_path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    for root, _dirs, files in os.walk(dir_path):
        for fname in sorted(files):
            if fname.endswith(".py") or fname == MANIFEST_FILENAME:
                fpath = os.path.join(root, fname)
                relpath = os.path.relpath(fpath, dir_path)
                h.update(relpath.encode("utf-8"))
                with open(fpath, "rb") as f:
                    while chunk := f.read(8192):
                        h.update(chunk)
    return h.hexdigest()


def _extract_wheel(wheel_path: str, plugin_name: str) -> str:
    extract_dir = tempfile.mkdtemp(prefix=f"hfusion_plugin_{plugin_name}_")
    with zipfile.ZipFile(wheel_path, "r") as zf:
        zf.extractall(extract_dir)
    return extract_dir


def _parse_tool_specs_from_extracted(
    extract_dir: str, manifest: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Parse tool specs from JSON files in the extracted directory.

    Looks for:
      - tool_specs.json in the manifest
      - Individual tool_spec_*.json files
      - tool_specs field in hfusion_plugin.json

    Does NOT import any Python code.
    """
    specs = []

    # Check manifest for tool_specs
    manifest_specs = manifest.get("tool_specs", [])
    if isinstance(manifest_specs, list):
        for spec in manifest_specs:
            if isinstance(spec, dict) and "name" in spec:
                specs.append(spec)

    # Check for tool_spec_*.json files
    if os.path.isdir(extract_dir):
        for fname in os.listdir(extract_dir):
            if fname.startswith("tool_spec_") and fname.endswith(".json"):
                try:
                    fpath = os.path.join(extract_dir, fname)
                    with open(fpath, "r", encoding="utf-8") as f:
                        spec = json.load(f)
                    if isinstance(spec, dict) and "name" in spec:
                        specs.append(spec)
                except (json.JSONDecodeError, OSError):
                    pass

    return specs
