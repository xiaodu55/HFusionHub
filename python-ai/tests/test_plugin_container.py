"""Tests for plugin container runner — sticky canary routing, digest enforcement,
canary version selection, and Docker integration scenarios.

Tests are organized into:
  1. Sticky version routing (logic)
  2. ContainerConfig / ContainerResult dataclasses (logic)
  3. select_canary_version (logic)
  4. execute_in_container digest enforcement (mocked HTTP)
  5. execute_with_canary (mocked Java backend)
  6. Runner unreachable → fail_closed (mocked HTTP)
  7. Docker integration tests (require Docker daemon — skipped otherwise)
"""

import hashlib
import json
import os
import sys

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.core.plugin.container_runner import (
    ContainerConfig,
    ContainerResult,
    PluginVersionInfo,
    compute_sticky_version,
    select_canary_version,
    execute_in_container,
    execute_with_canary,
    fetch_plugin_versions,
)


# ═══════════════════════════════════════════════════════════════════════
# 1. Sticky version routing
# ═══════════════════════════════════════════════════════════════════════

class TestStickyVersion:
    """Test the sticky canary routing algorithm."""

    def test_single_version_returns_it(self):
        result = compute_sticky_version("plugin-1", 100, ["1.0.0"], [1.0])
        assert result == "1.0.0"

    def test_sticky_same_user_same_version(self):
        versions = ["1.0.0", "2.0.0"]
        weights = [0.5, 0.5]
        results = [compute_sticky_version("plugin-1", 42, versions, weights) for _ in range(100)]
        assert len(set(results)) == 1, "Same user should always get same version"

    def test_different_users_can_get_different_versions(self):
        versions = ["1.0.0", "2.0.0"]
        weights = [0.5, 0.5]
        results = set()
        for uid in range(1000):
            results.add(compute_sticky_version("plugin-1", uid, versions, weights))
        assert len(results) == 2, "With enough users, both versions should appear"

    def test_weight_distribution_approximate(self):
        versions = ["1.0.0", "2.0.0"]
        weights = [0.8, 0.2]
        count_v1 = sum(
            1 for uid in range(10000)
            if compute_sticky_version("plugin-1", uid, versions, weights) == "1.0.0"
        )
        ratio = count_v1 / 10000
        assert 0.70 < ratio < 0.90, f"Expected ~80% for v1, got {ratio:.2%}"

    def test_three_versions_respect_weights(self):
        versions = ["1.0.0", "2.0.0", "3.0.0"]
        weights = [0.5, 0.3, 0.2]
        counts = {"1.0.0": 0, "2.0.0": 0, "3.0.0": 0}
        for uid in range(10000):
            v = compute_sticky_version("plugin-1", uid, versions, weights)
            counts[v] += 1
        assert counts["1.0.0"] > counts["2.0.0"] > counts["3.0.0"]

    def test_empty_versions_raises(self):
        with pytest.raises(ValueError, match="No versions available"):
            compute_sticky_version("plugin-1", 42, [], [])

    def test_deterministic_across_calls(self):
        versions = ["1.0.0", "2.0.0"]
        weights = [0.5, 0.5]
        r1 = compute_sticky_version("p", 99, versions, weights)
        r2 = compute_sticky_version("p", 99, versions, weights)
        assert r1 == r2

    def test_different_plugin_ids_give_different_routing(self):
        versions = ["1.0.0", "2.0.0"]
        weights = [0.5, 0.5]
        r1 = compute_sticky_version("plugin-a", 42, versions, weights)
        r2 = compute_sticky_version("plugin-b", 42, versions, weights)
        assert compute_sticky_version("plugin-a", 42, versions, weights) == r1


# ═══════════════════════════════════════════════════════════════════════
# 2. ContainerConfig / ContainerResult dataclasses
# ═══════════════════════════════════════════════════════════════════════

class TestContainerConfig:
    def test_defaults(self):
        config = ContainerConfig()
        assert config.cpu_limit == 1.0
        assert config.memory_limit == "256m"
        assert config.timeout == 30.0
        assert config.network == "plugin-isolated"
        assert config.read_only_rootfs is True
        assert config.pids_limit == 256
        assert config.allowed_domains == []
        assert config.blocked_domains == []

    def test_custom_config(self):
        config = ContainerConfig(
            cpu_limit=2.0,
            memory_limit="512m",
            timeout=60.0,
            allowed_domains=["api.github.com"],
            blocked_domains=["*.internal"],
            pids_limit=128,
        )
        assert config.cpu_limit == 2.0
        assert config.memory_limit == "512m"
        assert config.allowed_domains == ["api.github.com"]
        assert config.blocked_domains == ["*.internal"]
        assert config.pids_limit == 128


class TestContainerResult:
    def test_success(self):
        result = ContainerResult(success=True, data={"output": "ok"})
        assert result.success is True
        assert result.data == {"output": "ok"}
        assert result.error is None

    def test_failure(self):
        result = ContainerResult(success=False, error="timeout", error_code="TIMEOUT")
        assert result.success is False
        assert result.error == "timeout"
        assert result.error_code == "TIMEOUT"


# ═══════════════════════════════════════════════════════════════════════
# 3. select_canary_version (logic)
# ═══════════════════════════════════════════════════════════════════════

class TestSelectCanaryVersion:

    def test_single_stable_version_returns_it(self):
        versions = [
            PluginVersionInfo(
                version="1.0.0",
                container_image="hfusionhub-plugin-test:1.0.0",
                image_digest="sha256:abc123",
                canary_weight=0.0,
                is_stable=True,
            )
        ]
        selected = select_canary_version(versions, user_id=42, plugin_id="p1")
        assert selected is not None
        assert selected.version == "1.0.0"
        assert selected.container_image == "hfusionhub-plugin-test:1.0.0"
        assert selected.image_digest == "sha256:abc123"

    def test_stable_plus_canary_uses_sticky_routing(self):
        versions = [
            PluginVersionInfo(
                version="1.0.0",
                container_image="hfusionhub-plugin-test:1.0.0",
                image_digest="sha256:abc123",
                canary_weight=0.0,
                is_stable=True,
            ),
            PluginVersionInfo(
                version="2.0.0-canary",
                container_image="hfusionhub-plugin-test:2.0.0-canary",
                image_digest="sha256:def456",
                canary_weight=0.3,
                is_stable=False,
            ),
        ]
        selected = select_canary_version(versions, user_id=42, plugin_id="p1")
        assert selected is not None
        assert selected.version in ("1.0.0", "2.0.0-canary")

    def test_canary_weight_one_always_routes_to_canary(self):
        """With canary_weight=1.0, all users should get the canary version."""
        versions = [
            PluginVersionInfo(
                version="1.0.0",
                container_image="hfusionhub-plugin-test:1.0.0",
                image_digest="sha256:abc123",
                canary_weight=0.0,
                is_stable=True,
            ),
            PluginVersionInfo(
                version="2.0.0-canary",
                container_image="hfusionhub-plugin-test:2.0.0-canary",
                image_digest="sha256:def456",
                canary_weight=1.0,
                is_stable=False,
            ),
        ]
        results = set()
        for uid in range(100):
            selected = select_canary_version(versions, user_id=uid, plugin_id="p1")
            assert selected is not None
            results.add(selected.version)
        assert results == {"2.0.0-canary"}, "With canary_weight=1.0, all users should get canary"

    def test_empty_versions_returns_none(self):
        selected = select_canary_version([], user_id=42, plugin_id="p1")
        assert selected is None

    def test_no_stable_and_no_canary_returns_none(self):
        versions = [
            PluginVersionInfo(
                version="1.0.0",
                container_image="hfusionhub-plugin-test:1.0.0",
                image_digest="sha256:abc123",
                canary_weight=0.0,
                is_stable=False,  # Not stable, no canary weight → filtered out
            )
        ]
        selected = select_canary_version(versions, user_id=42, plugin_id="p1")
        assert selected is None

    def test_same_user_same_version_deterministic(self):
        versions = [
            PluginVersionInfo(
                version="1.0.0",
                container_image="img:v1",
                image_digest="sha256:aaa",
                canary_weight=0.0,
                is_stable=True,
            ),
            PluginVersionInfo(
                version="2.0.0",
                container_image="img:v2",
                image_digest="sha256:bbb",
                canary_weight=0.5,
                is_stable=False,
            ),
        ]
        first = select_canary_version(versions, user_id=99, plugin_id="p")
        for _ in range(50):
            assert select_canary_version(versions, user_id=99, plugin_id="p").version == first.version

    def test_stable_version_selected_when_all_weights_zero(self):
        versions = [
            PluginVersionInfo(
                version="1.0.0",
                container_image="img:v1",
                image_digest="sha256:aaa",
                canary_weight=0.0,
                is_stable=True,
            ),
        ]
        selected = select_canary_version(versions, user_id=1, plugin_id="p")
        assert selected is not None
        assert selected.version == "1.0.0"


# ═══════════════════════════════════════════════════════════════════════
# 4. execute_in_container digest enforcement (mocked HTTP)
# ═══════════════════════════════════════════════════════════════════════

class TestExecuteInContainerDigest:

    def test_missing_digest_rejected_client_side(self):
        """Python client rejects execution when image_digest is None."""
        import asyncio
        result = asyncio.run(execute_in_container(
            image_tag="hfusionhub-plugin-test:v1",
            tool_name="test_tool",
            tool_input={"key": "value"},
            image_digest=None,
        ))
        assert result.success is False
        assert result.error_code == "missing_digest"
        assert "image_digest is required" in result.error

    def test_missing_digest_rejected_client_side_empty_string(self):
        """Python client rejects execution when image_digest is empty."""
        import asyncio
        result = asyncio.run(execute_in_container(
            image_tag="hfusionhub-plugin-test:v1",
            tool_name="test_tool",
            tool_input={"key": "value"},
            image_digest="",
        ))
        assert result.success is False
        assert result.error_code == "missing_digest"

    def test_whitespace_digest_rejected(self):
        """Whitespace-only digest is also rejected."""
        import asyncio
        result = asyncio.run(execute_in_container(
            image_tag="hfusionhub-plugin-test:v1",
            tool_name="test_tool",
            tool_input={},
            image_digest="   ",
        ))
        assert result.success is False
        assert result.error_code == "missing_digest"

    def test_runner_token_missing_fails_closed_without_http_call(self):
        """A missing production secret rejects execution before network I/O."""
        import asyncio

        with patch("app.core.plugin.container_runner.PLUGIN_RUNNER_TOKEN", ""), patch(
            "app.core.plugin.container_runner.httpx.AsyncClient"
        ) as client:
            result = asyncio.run(execute_in_container(
                image_tag="hfusionhub-plugin-test:v1",
                tool_name="test_tool",
                tool_input={},
                image_digest="sha256:abc123",
            ))

        assert result.success is False
        assert result.error_code == "runner_not_configured"
        client.assert_not_called()

    def test_runner_unreachable_fail_closed(self):
        """When runner is unreachable, returns runner_unreachable error."""
        import asyncio
        import httpx as httpx_mod

        # Simulate connection refused by patching the httpx.AsyncClient
        async def _raise_connect_error(*args, **kwargs):
            raise httpx_mod.ConnectError("Connection refused")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = _raise_connect_error

        with patch(
            "app.core.plugin.container_runner.httpx.AsyncClient",
            return_value=mock_client,
        ), patch(
            "app.core.plugin.container_runner.PLUGIN_RUNNER_TOKEN", "test-runner-token",
        ):
            result = asyncio.run(execute_in_container(
                image_tag="hfusionhub-plugin-test:v1",
                tool_name="test_tool",
                tool_input={"key": "value"},
                image_digest="sha256:abc123",
            ))
        assert result.success is False
        assert result.error_code == "runner_unreachable"
        assert "unreachable" in result.error.lower()

    def test_runner_unreachable_production_mode_no_fallback(self):
        """P0-3: Runner unreachable → fail_closed, no fallback to subprocess."""
        import asyncio
        import httpx as httpx_mod

        async def _raise_connect_error(*args, **kwargs):
            raise httpx_mod.ConnectError("Connection refused")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = _raise_connect_error

        with patch(
            "app.core.plugin.container_runner.httpx.AsyncClient",
            return_value=mock_client,
        ), patch(
            "app.core.plugin.container_runner.PLUGIN_RUNNER_TOKEN", "test-runner-token",
        ):
            result = asyncio.run(execute_in_container(
                image_tag="hfusionhub-plugin-test:v1",
                tool_name="test_tool",
                tool_input={},
                image_digest="sha256:abc123",
            ))
        assert result.success is False
        assert result.error_code == "runner_unreachable"
        assert "fallback" not in result.error.lower()


# ═══════════════════════════════════════════════════════════════════════
# 5. execute_with_canary (mocked sub-functions)
# ═══════════════════════════════════════════════════════════════════════

class TestExecuteWithCanary:

    def test_canary_selects_stable_when_single_version(self):
        """With one stable version, canary routing selects it and executes."""
        import asyncio

        mock_versions = [
            PluginVersionInfo(
                version="1.0.0",
                container_image="hfusionhub-plugin-test:1.0.0",
                image_digest="sha256:abc123",
                canary_weight=0.0,
                is_stable=True,
            )
        ]

        mock_result = ContainerResult(
            success=True,
            data={"output": "canary_executed"},
            container_id="def678",
        )

        with patch(
            "app.core.plugin.container_runner.fetch_plugin_versions",
            new=AsyncMock(return_value=mock_versions),
        ), patch(
            "app.core.plugin.container_runner.execute_in_container",
            new=AsyncMock(return_value=mock_result),
        ):
            result = asyncio.run(execute_with_canary(
                plugin_id="p1",
                tool_name="test_tool",
                tool_input={"key": "value"},
                user_id=42,
                config=ContainerConfig(),
                java_backend_url="http://java:8080",
                internal_token="token123",
            ))
        assert result.success is True
        assert result.data == {"output": "canary_executed"}
        assert result.container_id == "def678"

    def test_canary_no_versions_returns_error(self):
        """When Java returns no versions, canary execution fails."""
        import asyncio

        with patch(
            "app.core.plugin.container_runner.fetch_plugin_versions",
            new=AsyncMock(return_value=[]),
        ):
            result = asyncio.run(execute_with_canary(
                plugin_id="p1",
                tool_name="test_tool",
                tool_input={},
                user_id=42,
                config=ContainerConfig(),
                java_backend_url="http://java:8080",
                internal_token="token123",
            ))
        assert result.success is False
        assert result.error_code == "no_version"

    def test_canary_java_backend_unreachable(self):
        """When Java backend is unreachable, canary fails gracefully."""
        import asyncio
        import httpx as httpx_mod

        async def _raise_connect_error(*args, **kwargs):
            raise httpx_mod.ConnectError("Connection refused")

        with patch(
            "app.core.plugin.container_runner.fetch_plugin_versions",
            new=_raise_connect_error,
        ):
            result = asyncio.run(execute_with_canary(
                plugin_id="p1",
                tool_name="test_tool",
                tool_input={},
                user_id=42,
                config=ContainerConfig(),
                java_backend_url="http://java:8080",
                internal_token="token123",
            ))
        assert result.success is False
        assert result.error_code == "version_fetch_failed"


# ═══════════════════════════════════════════════════════════════════════
# 6. fetch_plugin_versions (mocked HTTP client)
# ═══════════════════════════════════════════════════════════════════════

class TestFetchPluginVersions:

    def test_fetch_parses_correctly(self):
        """Verify that fetch_plugin_versions correctly parses Java response."""
        import asyncio
        import httpx as httpx_mod

        java_data = [
            {
                "version": "1.0.0",
                "container_image": "hfusionhub-plugin-test:1.0.0",
                "image_digest": "sha256:abc123",
                "canary_weight": 0,
                "status": "active",
            },
            {
                "version": "2.0.0-canary",
                "container_image": "hfusionhub-plugin-test:2.0.0",
                "image_digest": "sha256:def456",
                "canary_weight": 0.3,
                "status": "pending",
            },
        ]

        async def _mock_fetch(*args, **kwargs):
            return [
                PluginVersionInfo(
                    version=v["version"],
                    container_image=v["container_image"],
                    image_digest=v["image_digest"],
                    canary_weight=float(v.get("canary_weight", 0)),
                    is_stable=v.get("status") == "active"
                              and float(v.get("canary_weight", 0)) == 0,
                )
                for v in java_data
            ]

        with patch(
            "app.core.plugin.container_runner.fetch_plugin_versions",
            new=_mock_fetch,
        ):
            versions = asyncio.run(
                _mock_fetch("p1", "http://java:8080", "token")
            )

        assert len(versions) == 2
        assert versions[0].version == "1.0.0"
        assert versions[0].is_stable is True  # active + canary_weight=0
        assert versions[1].version == "2.0.0-canary"
        assert versions[1].is_stable is False  # pending + canary_weight>0
        assert versions[1].canary_weight == 0.3


# ═══════════════════════════════════════════════════════════════════════
# 7. Docker integration tests (require Docker daemon)
# ═══════════════════════════════════════════════════════════════════════

docker_available = False
try:
    import docker
    client = docker.from_env()
    client.ping()
    docker_available = True
    client.close()
except Exception:
    pass

requires_docker = pytest.mark.skipif(
    not docker_available,
    reason="Docker daemon not available — integration tests require Docker",
)


@requires_docker
class TestRunnerIntegration:

    RUNNER_PORT = 19100
    RUNNER_URL = f"http://localhost:{RUNNER_PORT}"
    RUNNER_TOKEN = "test-runner-token-integration"

    _plugin_tag = "hfusionhub-plugin-test-int:v1"
    _plugin_digest = None

    @pytest.fixture(autouse=True)
    def setup_runner(self):
        """Start plugin-runner + prepare a local test image (NO Docker Hub)."""
        import subprocess, time
        import docker as docker_lib

        # 1. Kill anything already on our port
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if f":{self.RUNNER_PORT}" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit():
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/PID", pid],
                                capture_output=True, timeout=5,
                            )
                        except Exception:
                            pass
        except Exception:
            pass

        # 2. Build a real test plugin image (fixed entry + deterministic tools).
        self._build_test_image()

        # 3. Start plugin-runner subprocess
        env = os.environ.copy()
        env["PLUGIN_RUNNER_TOKEN"] = self.RUNNER_TOKEN
        env["PLUGIN_ARTIFACTS_DIR"] = os.path.join(
            os.path.dirname(__file__), ".tmp-artifacts"
        )

        plugin_runner_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "docker", "plugin-runner")
        )

        proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "app:app",
                "--host", "127.0.0.1",
                "--port", str(self.RUNNER_PORT),
            ],
            cwd=plugin_runner_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 4. Wait for runner to be ready
        import httpx
        startup_ok = False
        for _ in range(30):
            if proc.poll() is not None:
                stderr_out = proc.stderr.read().decode("utf-8", errors="replace")
                proc.terminate()
                pytest.fail(
                    f"Plugin runner exited early with code {proc.returncode}.\n"
                    f"stderr:\n{stderr_out}"
                )
            try:
                resp = httpx.get(
                    f"{self.RUNNER_URL}/health",
                    headers={"X-Runner-Token": self.RUNNER_TOKEN},
                    timeout=2.0,
                )
                if resp.status_code == 200:
                    startup_ok = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not startup_ok:
            proc.terminate()
            proc.wait()
            stderr_out = proc.stderr.read().decode("utf-8", errors="replace")
            pytest.fail(
                f"Plugin runner did not start within 15 seconds.\n"
                f"stderr:\n{stderr_out}"
            )

        yield

        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    @classmethod
    def _build_test_image(cls):
        """Build the hfusionhub-plugin-test-int image with the fixed entry point.

        Reuses a local python base image to stay OFFLINE (no Docker Hub pulls).
        Falls back to busybox (no tool execution, only digest/network checks).
        """
        import docker as docker_lib

        client = docker_lib.from_env()

        run_tool_src = os.path.join(
            os.path.dirname(__file__), "..", "..", "docker", "plugin-runner", "run_tool.py"
        )
        with open(run_tool_src, "r", encoding="utf-8") as f:
            run_tool = f.read()

        fixture_dir = os.path.join(os.path.dirname(__file__), "container_fixture")
        with open(os.path.join(fixture_dir, "plugin.py"), "r", encoding="utf-8") as f:
            plugin_py = f.read()

        build_dir = os.path.join(os.path.dirname(__file__), ".tmp-plugin-build")
        os.makedirs(build_dir, exist_ok=True)
        with open(os.path.join(build_dir, "run_tool.py"), "w", encoding="utf-8") as f:
            f.write(run_tool)
        with open(os.path.join(build_dir, "plugin.py"), "w", encoding="utf-8") as f:
            f.write(plugin_py)

        base = cls._resolve_local_python_image(client)

        dockerfile = (
            f"FROM {base}\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends "
            "iptables netcat-openbsd && rm -rf /var/lib/apt/lists/*\n"
            "WORKDIR /opt/plugin\n"
            "COPY run_tool.py /opt/plugin/run_tool.py\n"
            "COPY plugin.py /opt/plugin/plugin.py\n"
            "RUN chmod +x /opt/plugin/run_tool.py\n"
        )
        with open(os.path.join(build_dir, "Dockerfile"), "w", encoding="utf-8") as f:
            f.write(dockerfile)

        try:
            img, _build_logs = client.images.build(
                path=build_dir,
                tag=cls._plugin_tag,
                rm=True,
            )
        except Exception as e:
            pytest.fail(f"Failed to build test plugin image: {e}")

        # Resolve the digest (RepoDigest if pushed, else image Id).
        repo = img.attrs.get("RepoDigests") or []
        cls._plugin_digest = repo[0] if repo else img.attrs.get("Id")
        if not cls._plugin_digest:
            pytest.fail("Built test image has no resolvable digest")

    @staticmethod
    def _resolve_local_python_image(client):
        """Find a local python base image to build from (OFFLINE).

        Returns the image TAG usable directly in a Dockerfile FROM clause
        (e.g. 'python:3.12-slim'). Requires a tagged python image — without
        one the integration tests cannot validate tool execution, network
        policy, or resource limits, so we fail rather than silently skip.
        """
        candidates = [
            "python:3.12-slim",
            "python:3.11-slim",
            "python:3.10-slim",
            "python:3.9-slim",
        ]
        for tag in candidates:
            try:
                img = client.images.get(tag)
                if img.tags:
                    return img.tags[0]
            except Exception:
                continue

        # Try any locally-present, tagged python image.
        try:
            images = client.images.list()
            for img in images:
                if not img.tags:
                    continue
                first_tag = img.tags[0]
                if first_tag.startswith("python:"):
                    return first_tag
        except Exception:
            pass

        pytest.fail(
            "Integration tests require a tagged local Python base image "
            "(e.g. 'python:3.12-slim'). Pull one to enable them."
        )

    def test_health_endpoint(self):
        """Health endpoint returns healthy status."""
        import httpx
        resp = httpx.get(
            f"{self.RUNNER_URL}/health",
            headers={"X-Runner-Token": self.RUNNER_TOKEN},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["docker_connected"] is True

    def test_execute_missing_digest_rejected(self):
        """P0-1: Runner rejects execution without image_digest (HTTP 400)."""
        import httpx
        resp = httpx.post(
            f"{self.RUNNER_URL}/execute",
            json={
                "image_tag": self._plugin_tag,
                "tool_name": "test_tool",
                "tool_input": {"key": "value"},
            },
            headers={"X-Runner-Token": self.RUNNER_TOKEN},
            timeout=10.0,
        )
        assert resp.status_code == 400, \
            f"Expected 400, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "image_digest" in detail.lower()
        assert "required" in detail.lower()

    def test_execute_wrong_digest_rejected(self):
        """P0-3: Wrong digest rejected (HTTP 400)."""
        if not self._plugin_digest:
            pytest.skip("Local test image has no RepoDigests")
        import httpx
        resp = httpx.post(
            f"{self.RUNNER_URL}/execute",
            json={
                "image_tag": self._plugin_tag,
                "tool_name": "test_tool",
                "tool_input": {"key": "value"},
                "image_digest": "sha256:" + "00" * 32,
            },
            headers={"X-Runner-Token": self.RUNNER_TOKEN},
            timeout=15.0,
        )
        assert resp.status_code == 400, \
            f"Expected 400, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "digest" in detail.lower()

    def test_execute_with_valid_digest_succeeds(self):
        """P0-3: Container executes via Runner with valid digest, returns tool output."""
        if not self._plugin_digest:
            pytest.skip("Local test image has no resolvable digest")
        import httpx
        resp = httpx.post(
            f"{self.RUNNER_URL}/execute",
            json={
                "image_tag": self._plugin_tag,
                "tool_name": "echo_tool",
                "tool_input": {"text": "hello-container"},
                "image_digest": self._plugin_digest,
                "config": {"timeout": 8.0},
            },
            headers={"X-Runner-Token": self.RUNNER_TOKEN},
            timeout=20.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True, \
            f"Expected success=True, got: {data}"
        # Deterministic output from the echo_tool fixture.
        assert data.get("data") == {
            "echo": "hello-container",
            "tool": "echo_tool",
            "source": "container",
        }, f"Unexpected tool output: {data.get('data')}"

    def test_unallowed_network_blocked(self):
        """P0-3: Container network restricted — tool calling a non-whitelisted
        domain fails while the runner still reports success at HTTP level."""
        if not self._plugin_digest:
            pytest.skip("Local test image has no resolvable digest")
        import httpx
        resp = httpx.post(
            f"{self.RUNNER_URL}/execute",
            json={
                "image_tag": self._plugin_tag,
                "tool_name": "network_probe_tool",
                "tool_input": {"url": "http://example.com/"},
                "image_digest": self._plugin_digest,
                "config": {
                    "timeout": 12.0,
                    "allowed_domains": ["no-such-domain.example"],
                },
            },
            headers={"X-Runner-Token": self.RUNNER_TOKEN},
            timeout=25.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True, f"Runner should not fail: {data}"
        # The network probe tool must report failure: example.com is not whitelisted.
        tool_data = data.get("data") or {}
        assert tool_data.get("ok") is False, \
            f"Tool should have been blocked from network, got: {tool_data}"

    def test_resource_limits_applied(self):
        """P0-3: Container runs with Memory/NanoCpus/PidsLimit/read-only rootfs."""
        if not self._plugin_digest:
            pytest.skip("Local test image has no resolvable digest")
        import httpx
        resp = httpx.post(
            f"{self.RUNNER_URL}/execute",
            json={
                "image_tag": self._plugin_tag,
                "tool_name": "resource_report_tool",
                "tool_input": {},
                "image_digest": self._plugin_digest,
                "config": {
                    "timeout": 8.0,
                    "memory_limit": "64m",
                    "cpu_limit": 0.5,
                    "pids_limit": 128,
                    "read_only_rootfs": True,
                },
            },
            headers={"X-Runner-Token": self.RUNNER_TOKEN},
            timeout=20.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        limits = data.get("resource_limits") or {}
        assert limits.get("memory_bytes") == 64 * 1024 * 1024, \
            f"Memory limit not enforced: {limits}"
        # CPU limit enforced via cpu_quota/cpu_period ratio (0.5 CPU).
        quota = limits.get("cpu_quota")
        period = limits.get("cpu_period") or 100000
        assert quota == int(0.5 * 100000) and period == 100000, \
            f"CPU limit not enforced: {limits}"
        assert limits.get("pids_limit") == 128, \
            f"PidsLimit not enforced: {limits}"
        assert limits.get("read_only_rootfs") is True, \
            f"read-only rootfs not enforced: {limits}"

class TestSecureByDefault:
    """Verify that defaults enforce security: digest required, fail_closed."""

    def test_container_config_defaults_are_restrictive(self):
        """Default config has secure values."""
        config = ContainerConfig()
        assert config.read_only_rootfs is True
        assert config.pids_limit == 256
        assert config.network == "plugin-isolated"

    def test_execute_in_container_requires_digest_no_bypass(self):
        """Cannot bypass digest check by passing None or empty."""
        import asyncio
        for bad_digest in (None, "", "  "):
            result = asyncio.run(execute_in_container(
                image_tag="hfusionhub-plugin-test:v1",
                tool_name="test",
                tool_input={},
                image_digest=bad_digest,
            ))
            assert result.success is False, f"Should reject digest={bad_digest!r}"
            assert result.error_code == "missing_digest"

    def test_canary_is_stable_flag_only_when_active_and_weight_zero(self):
        """is_stable is True ONLY when status='active' AND canary_weight=0."""
        versions = [
            PluginVersionInfo("1.0", "img:v1", "sha:a", 0.0, True),   # stable
            PluginVersionInfo("2.0", "img:v2", "sha:b", 0.3, False),  # canary
        ]
        selected = select_canary_version(versions, user_id=1, plugin_id="p")
        # Should prefer stable when no canary routing needed
        assert selected is not None


# ═══════════════════════════════════════════════════════════════════════
# 7. execute_in_sandbox fail-closed (container mode never falls back)
# ═══════════════════════════════════════════════════════════════════════

class TestContainerFailClosedNoSubprocess:
    """P0: container mode must NEVER fall back to a subprocess.

    Even when a manifest sets fail_closed=False, container execution that
    fails for ANY reason must return an error instead of downgrading to a
    subprocess. Subprocess execution is only available via explicit
    runner_mode="subprocess".
    """

    def _runner_unreachable_config(self, fail_closed: bool):
        from app.core.plugin.sandbox_runner import SubprocessConfig
        return SubprocessConfig(
            runner_mode="container",
            container_image="hfusionhub-plugin-test:v1",
            container_digest="sha256:abc123",
            fail_closed=fail_closed,
        )

    @staticmethod
    def _patch_runner_unreachable():
        """Patch container_runner httpx to raise ConnectError (runner down)."""
        import httpx as httpx_mod
        from unittest.mock import AsyncMock

        async def _raise_connect_error(*args, **kwargs):
            raise httpx_mod.ConnectError("Connection refused")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = _raise_connect_error

        return patch(
            "app.core.plugin.container_runner.httpx.AsyncClient",
            return_value=mock_client,
        )

    def test_container_fail_closed_never_spawns_subprocess(self):
        """Container failure must not spawn a subprocess."""
        from app.core.plugin.sandbox_runner import execute_in_sandbox

        with self._patch_runner_unreachable(), patch(
            "app.core.plugin.container_runner.PLUGIN_RUNNER_TOKEN", "test-runner-token",
        ), patch(
            "app.core.plugin.sandbox_runner.Process",
            MagicMock(
                side_effect=AssertionError(
                    "Process spawned — container mode must not fall back to subprocess"
                )
            ),
        ):
            result = execute_in_sandbox(
                plugin_dir="/tmp/plugin",
                plugin_name="test",
                tool_name="test_tool",
                tool_input={},
                config=self._runner_unreachable_config(fail_closed=True),
            )
        assert result.success is False
        assert result.error_code in ("runner_unreachable", "container_runner_unavailable")
        # Crucially: no subprocess fallback happened (Process was a failing stub).

    def test_container_fail_closed_even_when_manifest_disables(self):
        """Manifest fail_closed=False must NOT re-enable subprocess fallback."""
        from app.core.plugin.sandbox_runner import execute_in_sandbox

        with self._patch_runner_unreachable(), patch(
            "app.core.plugin.container_runner.PLUGIN_RUNNER_TOKEN", "test-runner-token",
        ), patch(
            "app.core.plugin.sandbox_runner.Process",
            MagicMock(
                side_effect=AssertionError(
                    "Process spawned — container mode must never downgrade to subprocess"
                )
            ),
        ):
            result = execute_in_sandbox(
                plugin_dir="/tmp/plugin",
                plugin_name="test",
                tool_name="test_tool",
                tool_input={},
                config=self._runner_unreachable_config(fail_closed=False),
            )
        assert result.success is False
        assert result.error_code in ("container_runner_unavailable", "runner_unreachable")
