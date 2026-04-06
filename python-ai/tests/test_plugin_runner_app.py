"""Regression tests for the standalone plugin-runner service module."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.responses import Response


@pytest.fixture(scope="module")
def runner_app():
    path = Path(__file__).parents[2] / "docker" / "plugin-runner" / "app.py"
    spec = importlib.util.spec_from_file_location("hfh_plugin_runner_app", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_network_rules_apply_ip_and_cidr_without_dns_lookup(runner_app):
    config = runner_app.ContainerConfig(
        allowed_domains=["203.0.113.0/24"],
        blocked_domains=["198.51.100.8"],
    )

    commands = runner_app._build_network_commands(config)

    assert "iptables -A OUTPUT -d 203.0.113.0/24 -j ACCEPT" in commands
    assert "iptables -A OUTPUT -d 198.51.100.8 -j DROP" in commands
    assert all("dig +short 203.0.113.0/24" not in command for command in commands)


@pytest.mark.parametrize("target", ["example.com; id", "$(id)", "example.com && id", ""])
def test_network_rules_reject_shell_metacharacters(runner_app, target):
    config = runner_app.ContainerConfig(allowed_domains=[target])

    with pytest.raises(HTTPException) as exc:
        runner_app._build_network_commands(config)

    assert exc.value.status_code == 400


def test_health_uses_allowlist_glob(runner_app, monkeypatch):
    images = MagicMock()
    images.list.return_value = [MagicMock()]
    docker_client = MagicMock(images=images)
    monkeypatch.setattr(runner_app, "_check_docker", lambda: True)
    monkeypatch.setattr(runner_app, "_get_docker", lambda: docker_client)

    result = asyncio.run(runner_app.health(Response()))

    images.list.assert_called_once_with("hfusionhub-plugin-*")
    assert result.docker_connected is True
    assert result.images_count == 1


def test_list_images_uses_allowlist_glob(runner_app, monkeypatch):
    image = MagicMock()
    image.tags = ["hfusionhub-plugin-demo:v1", "unrelated:v1"]
    image.short_id = "sha256:demo"
    image.attrs = {"Size": 1, "Created": "now"}
    images = MagicMock()
    images.list.return_value = [image]
    monkeypatch.setattr(runner_app, "_get_docker", lambda: MagicMock(images=images))
    monkeypatch.setattr(runner_app, "PLUGIN_RUNNER_TOKEN", "test-token")

    result = asyncio.run(runner_app.list_images("test-token"))

    images.list.assert_called_once_with("hfusionhub-plugin-*")
    assert result["total"] == 1
    assert result["images"] == [{
        "tag": "hfusionhub-plugin-demo:v1",
        "id": "sha256:demo",
        "size": 1,
        "created": "now",
    }]
