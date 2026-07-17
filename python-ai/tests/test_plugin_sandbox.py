"""Tests for plugin sandbox constraints."""

import os

import pytest

from app.core.plugin.sandbox import (
    FilesystemConfig,
    NetworkConfig,
    PluginSandbox,
    ResourceConfig,
    SandboxedHttpClient,
    SandboxedPathResolver,
    SandboxViolation,
)

# ── Network sandbox ──────────────────────────────────────────────────

class TestNetworkSandbox:
    def test_allowed_domain_passes(self):
        config = NetworkConfig(allowed_domains=["api.github.com"])
        client = SandboxedHttpClient(config)
        client.check_url("https://api.github.com/repos")  # should not raise

    def test_allowed_domain_with_wildcard(self):
        config = NetworkConfig(allowed_domains=["*.github.com"])
        client = SandboxedHttpClient(config)
        client.check_url("https://api.github.com/repos")

    def test_blocked_domain_raises(self):
        config = NetworkConfig(blocked_domains=["evil.com"])
        client = SandboxedHttpClient(config)
        with pytest.raises(SandboxViolation) as exc_info:
            client.check_url("https://evil.com/malware")
        assert exc_info.value.constraint == "network"

    def test_allowed_list_blocks_non_matching(self):
        config = NetworkConfig(allowed_domains=["api.github.com"])
        client = SandboxedHttpClient(config)
        with pytest.raises(SandboxViolation):
            client.check_url("https://evil.com/data")

    def test_empty_config_allows_all(self):
        config = NetworkConfig()
        client = SandboxedHttpClient(config)
        client.check_url("https://anything.com/path")  # should not raise

    def test_blocked_takes_precedence_over_allowed(self):
        config = NetworkConfig(
            allowed_domains=["*.github.com"],
            blocked_domains=["secret.github.com"],
        )
        client = SandboxedHttpClient(config)
        with pytest.raises(SandboxViolation):
            client.check_url("https://secret.github.com/data")

    def test_get_timeout(self):
        config = NetworkConfig(timeout_seconds=15.0)
        client = SandboxedHttpClient(config)
        assert client.get_timeout() == 15.0


# ── Filesystem sandbox ───────────────────────────────────────────────

class TestFilesystemSandbox:
    def test_allowed_path_passes(self, tmp_path):
        config = FilesystemConfig(allowed_paths=[str(tmp_path / "**")])
        resolver = SandboxedPathResolver(config)
        result = resolver.resolve(str(tmp_path / "data.txt"))
        assert result == str(tmp_path / "data.txt")

    def test_blocked_path_raises(self, tmp_path):
        config = FilesystemConfig(blocked_paths=[str(tmp_path / "secret*")])
        resolver = SandboxedPathResolver(config)
        with pytest.raises(SandboxViolation):
            resolver.resolve(str(tmp_path / "secret.txt"))

    def test_read_only_detection(self, tmp_path):
        config = FilesystemConfig(read_only_paths=[str(tmp_path / "**")])
        resolver = SandboxedPathResolver(config)
        assert resolver.is_read_only(str(tmp_path / "file.txt")) is True
        assert resolver.is_read_only("/tmp/other.txt") is False

    def test_empty_config_allows_all(self):
        config = FilesystemConfig()
        resolver = SandboxedPathResolver(config)
        result = resolver.resolve(os.path.join(os.sep, "tmp", "some", "path"))
        # On Windows, realpath converts /tmp to D:\tmp
        assert "tmp" in result and "some" in result


# ── Resource limits ──────────────────────────────────────────────────

class TestResourceLimits:
    def test_config_defaults(self):
        config = ResourceConfig()
        assert config.cpu_seconds == 10.0
        assert config.memory_mb == 256
        assert config.timeout_seconds == 30.0
        assert config.max_open_files == 64

    def test_custom_config(self):
        config = ResourceConfig(cpu_seconds=5.0, memory_mb=128, timeout_seconds=10.0)
        assert config.cpu_seconds == 5.0
        assert config.memory_mb == 128


# ── PluginSandbox composite ─────────────────────────────────────────

class TestPluginSandbox:
    def test_from_dict(self):
        data = {
            "network": {"allowed_domains": ["api.example.com"]},
            "filesystem": {"allowed_paths": ["/tmp/**"]},
            "resources": {"cpu_seconds": 5},
        }
        sandbox = PluginSandbox.from_config_dict(data)
        assert sandbox.network is not None
        assert sandbox.filesystem is not None
        assert sandbox.resources is not None

    def test_empty_config(self):
        sandbox = PluginSandbox.from_config_dict({})
        assert sandbox.network is None
        assert sandbox.filesystem is None
        assert sandbox.resources is None

    def test_get_http_client_raises_when_not_configured(self):
        sandbox = PluginSandbox.from_config_dict({})
        with pytest.raises(SandboxViolation):
            sandbox.get_http_client()

    def test_check_all_with_url(self):
        data = {"network": {"allowed_domains": ["api.example.com"]}}
        sandbox = PluginSandbox.from_config_dict(data)
        sandbox.check_all(url="https://api.example.com/data")  # should not raise

    def test_check_all_blocks_url(self):
        data = {"network": {"allowed_domains": ["api.example.com"]}}
        sandbox = PluginSandbox.from_config_dict(data)
        with pytest.raises(SandboxViolation):
            sandbox.check_all(url="https://evil.com/data")

    def test_check_all_with_path(self, tmp_path):
        data = {"filesystem": {"allowed_paths": [str(tmp_path / "**")]}}
        sandbox = PluginSandbox.from_config_dict(data)
        sandbox.check_all(path=str(tmp_path / "file.txt"))

    def test_from_dict_partial_config(self):
        data = {"network": {"blocked_domains": ["evil.com"]}}
        sandbox = PluginSandbox.from_config_dict(data)
        assert sandbox.network is not None
        assert sandbox.filesystem is None
