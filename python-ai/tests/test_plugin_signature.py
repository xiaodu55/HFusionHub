"""Tests for supply chain signature verification."""

import json
import os
import tempfile
import zipfile

import pytest

from app.core.plugin.signature import (
    compute_artifact_hash,
    compute_manifest_hash,
    register_trusted_key,
    revoke_key,
    is_key_revoked,
    is_key_trusted,
    list_trusted_keys,
    reset_policy,
    sign_plugin,
    verify_signature,
    SignatureError,
    UntrustedPublisherError,
    RevokedKeyError,
    SignatureNotFoundError,
)


@pytest.fixture(autouse=True)
def _clean_policy(tmp_path, monkeypatch):
    """Isolate trust policy for each test."""
    monkeypatch.setenv("HFUSIONHUB_PLUGIN_TRUST_DIR", str(tmp_path / "trust"))
    reset_policy()
    yield
    reset_policy()


def _make_wheel(tmp_path, name="test_plugin", version="1.0.0"):
    """Create a minimal wheel with manifest."""
    manifest = {
        "name": name,
        "version": version,
        "description": f"Test plugin {name}",
        "author": "test",
    }
    wheel_path = tmp_path / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(str(wheel_path), "w") as zf:
        zf.writestr("hfusion_plugin.json", json.dumps(manifest))
        zf.writestr(f"{name}/__init__.py", "def hello(): return 'world'")
    return str(wheel_path), manifest


def _generate_keypair():
    """Generate Ed25519 keypair for testing."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import base64

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_b64 = base64.b64encode(public_bytes).decode("utf-8")
    return private_key, private_pem, public_b64


# ── Hash functions ───────────────────────────────────────────────────

class TestHashFunctions:
    def test_compute_artifact_hash(self, tmp_path):
        path = tmp_path / "test.bin"
        path.write_bytes(b"hello world")
        h = compute_artifact_hash(str(path))
        assert len(h) == 64
        assert h == compute_artifact_hash(str(path))  # deterministic

    def test_compute_manifest_hash(self):
        m = {"name": "test", "version": "1.0.0"}
        h = compute_manifest_hash(m)
        assert len(h) == 64
        assert h == compute_manifest_hash(m)  # deterministic

    def test_manifest_hash_order_independent(self):
        m1 = {"name": "test", "version": "1.0.0", "description": "d"}
        m2 = {"description": "d", "name": "test", "version": "1.0.0"}
        assert compute_manifest_hash(m1) == compute_manifest_hash(m2)


# ── Trust policy ─────────────────────────────────────────────────────

class TestTrustPolicy:
    def test_register_and_list_trusted_key(self):
        register_trusted_key("Publisher A", "abc123==", email="a@test.com")
        keys = list_trusted_keys()
        assert "abc123==" in keys
        assert keys["abc123=="]["name"] == "Publisher A"
        assert keys["abc123=="]["email"] == "a@test.com"

    def test_is_key_trusted(self):
        assert not is_key_trusted("abc123==")
        register_trusted_key("Publisher A", "abc123==")
        assert is_key_trusted("abc123==")

    def test_revoke_key(self):
        register_trusted_key("Publisher A", "abc123==")
        assert is_key_trusted("abc123==")

        revoke_key("abc123==", reason="compromised")
        assert not is_key_trusted("abc123==")
        assert is_key_revoked("abc123==")

    def test_revoked_key_not_trusted(self):
        revoke_key("key1", reason="test")
        assert not is_key_trusted("key1")
        assert is_key_revoked("key1")

    def test_multiple_keys(self):
        register_trusted_key("A", "key_a")
        register_trusted_key("B", "key_b")
        keys = list_trusted_keys()
        assert len(keys) == 2


# ── Sign + verify roundtrip ─────────────────────────────────────────

class TestSignAndVerify:
    def test_sign_and_verify_roundtrip(self, tmp_path):
        wheel_path, manifest = _make_wheel(tmp_path)
        private_key, private_pem, public_b64 = _generate_keypair()

        # Write private key
        key_path = tmp_path / "private.pem"
        key_path.write_bytes(private_pem)

        # Sign
        sig_path = sign_plugin(wheel_path, manifest, str(key_path))
        assert os.path.exists(sig_path)

        # Register key as trusted
        register_trusted_key("Test Publisher", public_b64)

        # Verify
        assert verify_signature(wheel_path, manifest) is True

    def test_verify_fails_with_wrong_key(self, tmp_path):
        wheel_path, manifest = _make_wheel(tmp_path)
        private_key, private_pem, public_b64 = _generate_keypair()

        key_path = tmp_path / "private.pem"
        key_path.write_bytes(private_pem)
        sign_plugin(wheel_path, manifest, str(key_path))

        # Register DIFFERENT key as trusted
        _, _, other_b64 = _generate_keypair()
        register_trusted_key("Other", other_b64)

        with pytest.raises(UntrustedPublisherError):
            verify_signature(wheel_path, manifest)

    def test_verify_fails_with_revoked_key(self, tmp_path):
        wheel_path, manifest = _make_wheel(tmp_path)
        private_key, private_pem, public_b64 = _generate_keypair()

        key_path = tmp_path / "private.pem"
        key_path.write_bytes(private_pem)
        sign_plugin(wheel_path, manifest, str(key_path))

        register_trusted_key("Publisher", public_b64)
        revoke_key(public_b64, reason="compromised")

        with pytest.raises(RevokedKeyError):
            verify_signature(wheel_path, manifest)

    def test_verify_fails_with_tampered_manifest(self, tmp_path):
        wheel_path, manifest = _make_wheel(tmp_path)
        private_key, private_pem, public_b64 = _generate_keypair()

        key_path = tmp_path / "private.pem"
        key_path.write_bytes(private_pem)
        sign_plugin(wheel_path, manifest, str(key_path))

        register_trusted_key("Publisher", public_b64)

        # Tamper with manifest
        tampered = {**manifest, "version": "2.0.0"}
        with pytest.raises(SignatureError, match="manifest 哈希不匹配"):
            verify_signature(wheel_path, tampered)

    def test_verify_fails_with_missing_sig(self, tmp_path):
        wheel_path, manifest = _make_wheel(tmp_path)

        with pytest.raises(SignatureNotFoundError):
            verify_signature(wheel_path, manifest)


# ── Fail-closed when cryptography unavailable ────────────────────────

class TestFailClosed:
    def test_loader_rejects_install_when_cryptography_missing(self, tmp_path, monkeypatch):
        """load_plugin_from_wheel must reject when verify_sig=True and _HAS_SIGNATURE=False."""
        import app.core.plugin.loader as loader_mod

        wheel_path, manifest = _make_wheel(tmp_path)

        # Force _HAS_SIGNATURE to False (simulates missing cryptography)
        monkeypatch.setattr(loader_mod, "_HAS_SIGNATURE", False)

        with pytest.raises(Exception, match="签名验证不可用"):
            loader_mod.load_plugin_from_wheel(
                str(wheel_path),
                require_hash=False,
                verify_sig=True,
            )

    def test_loader_allows_skip_when_verify_sig_false(self, tmp_path, monkeypatch):
        """load_plugin_from_wheel must pass when verify_sig=False regardless of _HAS_SIGNATURE."""
        import app.core.plugin.loader as loader_mod

        wheel_path, manifest = _make_wheel(tmp_path)
        monkeypatch.setattr(loader_mod, "_HAS_SIGNATURE", False)

        # Should NOT raise — skip verification explicitly
        descriptor = loader_mod.load_plugin_from_wheel(
            str(wheel_path),
            require_hash=False,
            verify_sig=False,
        )
        assert descriptor.name == "test_plugin"
