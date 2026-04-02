"""Plugin manifest validation + SHA-256 integrity verification.

A valid manifest declares:
  - name (str, machine-readable, e.g. "github_connector")
  - version (str, semver)
  - description (str)
  - permissions (list[str], optional)
  - sandbox (dict, optional)
  - dependencies (list[dict], optional)

Integrity:
  - compute_manifest_hash(manifest) → SHA-256 hex string
  - validate_manifest(manifest) → raises ManifestValidationError on failure
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Constants ────────────────────────────────────────────────────────

REQUIRED_MANIFEST_FIELDS = {"name", "version", "description"}

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

VALID_SOURCES = {"local", "git", "wheel"}

# Sandbox constraint keys
SANDBOX_NETWORK_KEYS = {"allowed_domains", "blocked_domains", "timeout_seconds"}
SANDBOX_FILESYSTEM_KEYS = {"allowed_paths", "blocked_paths", "read_only_paths"}
SANDBOX_RESOURCE_KEYS = {"cpu_seconds", "memory_mb", "max_open_files"}


# ── Errors ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ManifestValidationError:
    """Structured validation error for callers to inspect."""
    field: str
    message: str

    def __str__(self) -> str:
        return f"manifest.{self.field}: {self.message}"


class ManifestError(Exception):
    """Raised when manifest validation fails.  Wraps one or more ManifestValidationError."""

    def __init__(self, errors: List[ManifestValidationError]):
        self.errors = errors
        super().__init__(f"Manifest 验证失败: {'; '.join(str(e) for e in errors)}")


# ── Hash ─────────────────────────────────────────────────────────────

def compute_manifest_hash(manifest: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of the manifest JSON.

    The canonical form sorts keys, uses compact separators, and ensures
    ASCII encoding for reproducibility across platforms.
    """
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Validation ───────────────────────────────────────────────────────

def validate_manifest(manifest: Dict[str, Any]) -> None:
    """Validate a plugin manifest.  Raises ManifestError on failure.

    Checks:
      1. Required fields present and non-empty
      2. Version is valid semver
      3. Source is in allowed set
      4. Permissions is list of non-empty strings
      5. Sandbox config is valid dict (if present)
      6. Dependencies is list of dicts with 'name' key (if present)
    """
    errors: List[ManifestValidationError] = []

    # 1. Required fields
    for field_name in REQUIRED_MANIFEST_FIELDS:
        val = manifest.get(field_name)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(ManifestValidationError(field_name, "必填字段缺失或为空"))

    # 2. Semver
    version = manifest.get("version")
    if version and not _SEMVER_RE.match(str(version)):
        errors.append(ManifestValidationError("version", f"无效的语义化版本: {version}"))

    # 3. Source
    source = manifest.get("source", "local")
    if source not in VALID_SOURCES:
        errors.append(ManifestValidationError("source", f"无效来源: {source}，允许值: {VALID_SOURCES}"))

    # 4. Permissions
    perms = manifest.get("permissions")
    if perms is not None:
        if not isinstance(perms, list):
            errors.append(ManifestValidationError("permissions", "permissions 必须是字符串列表"))
        else:
            for i, p in enumerate(perms):
                if not isinstance(p, str) or not p.strip():
                    errors.append(ManifestValidationError(f"permissions[{i}]", "权限项必须是非空字符串"))

    # 5. Sandbox
    sandbox = manifest.get("sandbox")
    if sandbox is not None:
        if not isinstance(sandbox, dict):
            errors.append(ManifestValidationError("sandbox", "sandbox 必须是字典"))
        else:
            _validate_sandbox(sandbox, errors)

    # 6. Dependencies
    deps = manifest.get("dependencies")
    if deps is not None:
        if not isinstance(deps, list):
            errors.append(ManifestValidationError("dependencies", "dependencies 必须是列表"))
        else:
            for i, dep in enumerate(deps):
                if not isinstance(dep, dict) or "name" not in dep:
                    errors.append(ManifestValidationError(f"dependencies[{i}]", "依赖项必须包含 'name' 字段"))

    if errors:
        raise ManifestError(errors)


def _validate_sandbox(sandbox: Dict[str, Any], errors: List[ManifestValidationError]) -> None:
    """Validate sandbox constraint structure."""
    network = sandbox.get("network")
    if network is not None:
        if not isinstance(network, dict):
            errors.append(ManifestValidationError("sandbox.network", "必须是字典"))
        else:
            for key in network:
                if key not in SANDBOX_NETWORK_KEYS:
                    errors.append(ManifestValidationError(f"sandbox.network.{key}", f"未知网络约束: {key}"))
            allowed = network.get("allowed_domains")
            if allowed is not None and not isinstance(allowed, list):
                errors.append(ManifestValidationError("sandbox.network.allowed_domains", "必须是列表"))
            blocked = network.get("blocked_domains")
            if blocked is not None and not isinstance(blocked, list):
                errors.append(ManifestValidationError("sandbox.network.blocked_domains", "必须是列表"))

    filesystem = sandbox.get("filesystem")
    if filesystem is not None:
        if not isinstance(filesystem, dict):
            errors.append(ManifestValidationError("sandbox.filesystem", "必须是字典"))
        else:
            for key in filesystem:
                if key not in SANDBOX_FILESYSTEM_KEYS:
                    errors.append(ManifestValidationError(f"sandbox.filesystem.{key}", f"未知文件系统约束: {key}"))
            for path_key in ("allowed_paths", "blocked_paths", "read_only_paths"):
                val = filesystem.get(path_key)
                if val is not None and not isinstance(val, list):
                    errors.append(ManifestValidationError(f"sandbox.filesystem.{path_key}", "必须是列表"))

    resources = sandbox.get("resources")
    if resources is not None:
        if not isinstance(resources, dict):
            errors.append(ManifestValidationError("sandbox.resources", "必须是字典"))
        else:
            for key in resources:
                if key not in SANDBOX_RESOURCE_KEYS:
                    errors.append(ManifestValidationError(f"sandbox.resources.{key}", f"未知资源约束: {key}"))
                elif not isinstance(resources[key], (int, float)) or resources[key] < 0:
                    errors.append(ManifestValidationError(f"sandbox.resources.{key}", "必须是非负数"))


# ── Parsing helpers ──────────────────────────────────────────────────

def parse_manifest_json(raw: str) -> Dict[str, Any]:
    """Parse a JSON string into a manifest dict.  Raises ManifestError on invalid JSON."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ManifestError([ManifestValidationError("json", f"JSON 解析失败: {e}")])
