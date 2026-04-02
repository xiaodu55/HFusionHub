"""Tests for plugin manifest validation and SHA-256 integrity."""

import pytest
from app.core.plugin.manifest import (
    compute_manifest_hash,
    validate_manifest,
    ManifestError,
    ManifestValidationError,
)


# ── Hash tests ───────────────────────────────────────────────────────

class TestManifestHash:
    def test_hash_is_deterministic(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc"}
        h1 = compute_manifest_hash(m)
        h2 = compute_manifest_hash(m)
        assert h1 == h2

    def test_hash_is_sha256_hex(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc"}
        h = compute_manifest_hash(m)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_changes_with_different_keys(self):
        m1 = {"name": "test", "version": "1.0.0", "description": "desc"}
        m2 = {"name": "test", "version": "1.0.1", "description": "desc"}
        assert compute_manifest_hash(m1) != compute_manifest_hash(m2)

    def test_hash_key_order_independent(self):
        m1 = {"version": "1.0.0", "name": "test", "description": "desc"}
        m2 = {"name": "test", "description": "desc", "version": "1.0.0"}
        assert compute_manifest_hash(m1) == compute_manifest_hash(m2)


# ── Validation: required fields ──────────────────────────────────────

class TestManifestRequiredFields:
    def test_valid_minimal_manifest(self):
        m = {"name": "test_plugin", "version": "1.0.0", "description": "A test"}
        validate_manifest(m)  # should not raise

    def test_missing_name(self):
        m = {"version": "1.0.0", "description": "A test"}
        with pytest.raises(ManifestError) as exc_info:
            validate_manifest(m)
        assert any(e.field == "name" for e in exc_info.value.errors)

    def test_empty_name(self):
        m = {"name": "", "version": "1.0.0", "description": "A test"}
        with pytest.raises(ManifestError) as exc_info:
            validate_manifest(m)
        assert any(e.field == "name" for e in exc_info.value.errors)

    def test_missing_version(self):
        m = {"name": "test", "description": "A test"}
        with pytest.raises(ManifestError) as exc_info:
            validate_manifest(m)
        assert any(e.field == "version" for e in exc_info.value.errors)

    def test_missing_description(self):
        m = {"name": "test", "version": "1.0.0"}
        with pytest.raises(ManifestError) as exc_info:
            validate_manifest(m)
        assert any(e.field == "description" for e in exc_info.value.errors)

    def test_multiple_missing_fields(self):
        m = {}
        with pytest.raises(ManifestError) as exc_info:
            validate_manifest(m)
        assert len(exc_info.value.errors) >= 3


# ── Validation: semver ───────────────────────────────────────────────

class TestManifestSemver:
    @pytest.mark.parametrize("version", [
        "1.0.0", "0.1.0", "10.20.30", "1.0.0-alpha", "1.0.0-beta.1",
        "1.0.0+build.123", "1.0.0-rc.1+build",
    ])
    def test_valid_semver(self, version):
        m = {"name": "test", "version": version, "description": "desc"}
        validate_manifest(m)

    @pytest.mark.parametrize("version", [
        "1", "1.0", "v1.0.0", "1.0.0.0", "abc", "1.0.0_", "1.0.0-",
    ])
    def test_invalid_semver(self, version):
        m = {"name": "test", "version": version, "description": "desc"}
        with pytest.raises(ManifestError) as exc_info:
            validate_manifest(m)
        assert any(e.field == "version" for e in exc_info.value.errors)


# ── Validation: source ───────────────────────────────────────────────

class TestManifestSource:
    @pytest.mark.parametrize("source", ["local", "git", "wheel"])
    def test_valid_source(self, source):
        m = {"name": "test", "version": "1.0.0", "description": "desc", "source": source}
        validate_manifest(m)

    def test_invalid_source(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc", "source": "pypi"}
        with pytest.raises(ManifestError) as exc_info:
            validate_manifest(m)
        assert any(e.field == "source" for e in exc_info.value.errors)

    def test_default_source_is_local(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc"}
        validate_manifest(m)  # should not raise


# ── Validation: permissions ──────────────────────────────────────────

class TestManifestPermissions:
    def test_valid_permissions(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "permissions": ["web_access", "kb_write"]}
        validate_manifest(m)

    def test_invalid_permissions_not_list(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "permissions": "web_access"}
        with pytest.raises(ManifestError):
            validate_manifest(m)

    def test_invalid_permissions_empty_string(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "permissions": [""]}
        with pytest.raises(ManifestError):
            validate_manifest(m)


# ── Validation: sandbox ──────────────────────────────────────────────

class TestManifestSandbox:
    def test_valid_sandbox(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "sandbox": {
                 "network": {"allowed_domains": ["api.github.com"]},
                 "filesystem": {"allowed_paths": ["/tmp/**"]},
                 "resources": {"cpu_seconds": 10, "memory_mb": 256},
             }}
        validate_manifest(m)

    def test_invalid_sandbox_not_dict(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "sandbox": "invalid"}
        with pytest.raises(ManifestError):
            validate_manifest(m)

    def test_invalid_sandbox_unknown_network_key(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "sandbox": {"network": {"unknown_key": True}}}
        with pytest.raises(ManifestError):
            validate_manifest(m)

    def test_invalid_sandbox_negative_resource(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "sandbox": {"resources": {"cpu_seconds": -1}}}
        with pytest.raises(ManifestError):
            validate_manifest(m)


# ── Validation: dependencies ─────────────────────────────────────────

class TestManifestDependencies:
    def test_valid_dependencies(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "dependencies": [
                 {"name": "requests", "version": ">=2.0"},
                 {"name": "numpy", "optional": True},
             ]}
        validate_manifest(m)

    def test_invalid_dependency_not_dict(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "dependencies": ["requests"]}
        with pytest.raises(ManifestError):
            validate_manifest(m)

    def test_invalid_dependency_missing_name(self):
        m = {"name": "test", "version": "1.0.0", "description": "desc",
             "dependencies": [{"version": "1.0"}]}
        with pytest.raises(ManifestError):
            validate_manifest(m)
