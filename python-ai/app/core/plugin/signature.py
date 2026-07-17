"""Plugin supply chain signature verification.

Provides Ed25519-based code signing for plugin wheels with:
  - Trusted publisher allowlist (public key pinning)
  - Manifest integrity binding (manifest hash signed alongside artifact)
  - Revocation list for compromised keys
  - Verification at install time (mandatory) and load time (defense-in-depth)

Trust model:
  1. Publisher registers a public key with the platform (out-of-band).
  2. Publisher signs the wheel artifact + manifest hash using Ed25519.
  3. Installer verifies signature against the trusted allowlist before install.
  4. Loader re-verifies at load time to catch post-install tampering.
  5. Compromised keys are added to a revocation list checked at both stages.

File layout in the plugin wheel:
  - `hfusion_plugin.json` — manifest sidecar
  - `hfusion_plugin.sig` — base64-encoded Ed25519 signature over (manifest_json || artifact_sha256)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────

_SIG_FILENAME = "hfusion_plugin.sig"
_MANIFEST_FILENAME = "hfusion_plugin.json"
_ALLOWLIST_FILENAME = "trusted_publishers.json"
_REVOCATION_LIST_FILENAME = "revoked_keys.json"


# ── Errors ───────────────────────────────────────────────────────────

class SignatureError(Exception):
    """Raised when signature verification fails."""


class UntrustedPublisherError(SignatureError):
    """Raised when the signing key is not in the trusted allowlist."""


class RevokedKeyError(SignatureError):
    """Raised when the signing key has been revoked."""


class SignatureNotFoundError(SignatureError):
    """Raised when no signature file is found (only enforced when required)."""


# ── Data classes ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignatureBundle:
    """Contents of a .sig file."""
    algorithm: str  # "ed25519"
    public_key: str  # hex-encoded Ed25519 public key (base64)
    signature: str  # base64-encoded Ed25519 signature
    signed_at: float  # unix timestamp when signed
    manifest_hash: str  # SHA-256 of the manifest JSON
    artifact_hash: str  # SHA-256 of the wheel file


@dataclass
class TrustPolicy:
    """Platform trust policy for plugin signatures."""
    trusted_keys: dict[str, dict[str, Any]] = field(default_factory=dict)
    revoked_keys: set[str] = field(default_factory=set)
    require_signature: bool = True  # enforce signature on install
    allow_self_signed: bool = False  # never in production


# ── Trust policy persistence ────────────────────────────────────────

_policy: TrustPolicy | None = None
_policy_path: str | None = None


def _get_policy_path() -> str:
    global _policy_path
    if _policy_path is None:
        base = os.environ.get(
            "HFUSIONHUB_PLUGIN_TRUST_DIR",
            os.path.join(os.path.expanduser("~"), ".hfusionhub", "trust"),
        )
        _policy_path = os.path.join(base, "policy.json")
    return _policy_path


def _load_policy() -> TrustPolicy:
    global _policy
    if _policy is not None:
        return _policy

    path = _get_policy_path()
    policy = TrustPolicy()

    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            policy.trusted_keys = data.get("trusted_keys", {})
            policy.revoked_keys = set(data.get("revoked_keys", []))
            policy.require_signature = data.get("require_signature", True)
            policy.allow_self_signed = data.get("allow_self_signed", False)
        except Exception as e:
            logger.warning("加载信任策略失败: %s — 使用默认策略", e)

    _policy = policy
    return policy


def _save_policy(policy: TrustPolicy) -> None:
    global _policy
    _policy = policy
    path = _get_policy_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "trusted_keys": policy.trusted_keys,
        "revoked_keys": sorted(policy.revoked_keys),
        "require_signature": policy.require_signature,
        "allow_self_signed": policy.allow_self_signed,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def reset_policy() -> None:
    """Reset the loaded policy and cached path (used in tests)."""
    global _policy, _policy_path
    _policy = None
    _policy_path = None


# ── Key management ───────────────────────────────────────────────────

def register_trusted_key(
    name: str,
    public_key_b64: str,
    email: str | None = None,
    url: str | None = None,
) -> None:
    """Register a publisher's public key in the trust allowlist.

    Args:
        name: Human-readable publisher name (e.g., "HFusionHub Official").
        public_key_b64: Base64-encoded Ed25519 public key (32 bytes).
        email: Optional contact email.
        url: Optional publisher URL.
    """
    policy = _load_policy()
    # Normalize: strip whitespace, ensure consistent base64
    key_clean = public_key_b64.strip()
    policy.trusted_keys[key_clean] = {
        "name": name,
        "email": email,
        "url": url,
        "registered_at": time.time(),
    }
    _save_policy(policy)
    logger.info("已注册受信任发布者: %s (key=%s...)", name, key_clean[:12])


def revoke_key(public_key_b64: str, reason: str = "") -> None:
    """Revoke a previously trusted public key.

    Revoked keys are checked at both install and load time.
    """
    policy = _load_policy()
    key_clean = public_key_b64.strip()
    policy.revoked_keys.add(key_clean)
    # Remove from trusted list if present
    policy.trusted_keys.pop(key_clean, None)
    _save_policy(policy)
    logger.warning("已撤销发布者密钥: %s... reason=%s", key_clean[:12], reason)


def is_key_revoked(public_key_b64: str) -> bool:
    """Check if a key has been revoked."""
    policy = _load_policy()
    return public_key_b64.strip() in policy.revoked_keys


def is_key_trusted(public_key_b64: str) -> bool:
    """Check if a key is in the trusted allowlist."""
    policy = _load_policy()
    return public_key_b64.strip() in policy.trusted_keys


def list_trusted_keys() -> dict[str, dict[str, Any]]:
    """Return all trusted keys and their metadata."""
    policy = _load_policy()
    return dict(policy.trusted_keys)


# ── Signature creation ───────────────────────────────────────────────

def compute_artifact_hash(file_path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 of manifest JSON (canonical form)."""
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sign_plugin(
    wheel_path: str,
    manifest: dict[str, Any],
    private_key_path: str,
) -> str:
    """Sign a plugin wheel + manifest hash using Ed25519.

    Creates a `hfusion_plugin.sig` file alongside the wheel.

    Args:
        wheel_path: Path to the .whl file.
        manifest: The plugin manifest dict.
        private_key_path: Path to PEM-encoded Ed25519 private key.

    Returns:
        Path to the created .sig file.
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        raise SignatureError("需要安装 cryptography 库: pip install cryptography")

    # Compute hashes
    artifact_hash = compute_artifact_hash(wheel_path)
    manifest_hash = compute_manifest_hash(manifest)

    # Load private key
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    if not isinstance(private_key, Ed25519PrivateKey):
        raise SignatureError("私钥必须是 Ed25519 类型")

    # Sign: manifest_hash || artifact_hash
    payload = (manifest_hash + artifact_hash).encode("utf-8")
    signature = private_key.sign(payload)

    # Get public key
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    # Create signature bundle
    bundle = {
        "algorithm": "ed25519",
        "public_key": base64.b64encode(public_bytes).decode("utf-8"),
        "signature": base64.b64encode(signature).decode("utf-8"),
        "signed_at": time.time(),
        "manifest_hash": manifest_hash,
        "artifact_hash": artifact_hash,
    }

    # Write .sig file
    sig_path = wheel_path.rsplit(".", 1)[0] + ".sig"
    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)

    logger.info("插件签名已创建: %s", sig_path)
    return sig_path


# ── Signature verification ───────────────────────────────────────────

def verify_signature(
    wheel_path: str,
    manifest: dict[str, Any],
    sig_path: str | None = None,
    enforce_trust: bool = True,
) -> bool:
    """Verify the signature of a plugin wheel.

    Args:
        wheel_path: Path to the .whl file.
        manifest: The plugin manifest dict.
        sig_path: Path to the .sig file (auto-detected if None).
        enforce_trust: Whether to check against the trusted allowlist.

    Returns:
        True if signature is valid and trusted.

    Raises:
        SignatureError: If verification fails.
        UntrustedPublisherError: If key is not trusted.
        RevokedKeyError: If key has been revoked.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        raise SignatureError("需要安装 cryptography 库: pip install cryptography")

    # Find sig file
    if sig_path is None:
        sig_path = wheel_path.rsplit(".", 1)[0] + ".sig"

    if not os.path.exists(sig_path):
        policy = _load_policy()
        if policy.require_signature:
            raise SignatureNotFoundError(f"签名文件不存在: {sig_path}")
        logger.warning("签名文件不存在，跳过验证: %s", sig_path)
        return False

    # Load signature bundle
    with open(sig_path, encoding="utf-8") as f:
        bundle = json.load(f)

    if bundle.get("algorithm") != "ed25519":
        raise SignatureError(f"不支持的签名算法: {bundle.get('algorithm')}")

    # Revoke check
    pub_key_b64 = bundle["public_key"]
    if is_key_revoked(pub_key_b64):
        raise RevokedKeyError(f"签名密钥已被撤销: {pub_key_b64[:12]}...")

    # Trust check
    if enforce_trust and not is_key_trusted(pub_key_b64):
        policy = _load_policy()
        if not policy.allow_self_signed:
            raise UntrustedPublisherError(
                f"签名密钥不在受信任列表中: {pub_key_b64[:12]}... "
                f"请先注册: register_trusted_key(name, public_key_b64)"
            )

    # Reconstruct payload
    manifest_hash = compute_manifest_hash(manifest)
    artifact_hash = compute_artifact_hash(wheel_path)

    if bundle["manifest_hash"] != manifest_hash:
        raise SignatureError(
            f"manifest 哈希不匹配: 期望 {bundle['manifest_hash'][:16]}..., "
            f"实际 {manifest_hash[:16]}..."
        )

    if bundle["artifact_hash"] != artifact_hash:
        raise SignatureError(
            f"artifact 哈希不匹配: 期望 {bundle['artifact_hash'][:16]}..., "
            f"实际 {artifact_hash[:16]}..."
        )

    # Verify Ed25519 signature
    try:
        pub_bytes = base64.b64decode(pub_key_b64)
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)

        sig_bytes = base64.b64decode(bundle["signature"])
        payload = (manifest_hash + artifact_hash).encode("utf-8")

        public_key.verify(sig_bytes, payload)
    except Exception as e:
        raise SignatureError(f"签名验证失败: {e}")

    logger.info("插件签名验证通过: %s (publisher=%s)", wheel_path, pub_key_b64[:12])
    return True


def verify_at_load(wheel_path: str, manifest: dict[str, Any]) -> bool:
    """Verify signature at load time (defense-in-depth).

    Called during plugin loading to catch post-install tampering.
    Always enforces trust (no bypass).
    """
    try:
        return verify_signature(wheel_path, manifest, enforce_trust=True)
    except SignatureNotFoundError:
        # At load time, missing sig is a warning if trust policy allows
        policy = _load_policy()
        if policy.require_signature:
            raise
        logger.warning("加载时未找到签名文件: %s", wheel_path)
        return False
