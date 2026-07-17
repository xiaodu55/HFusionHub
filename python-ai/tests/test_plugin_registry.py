"""Tests for plugin registry (in-memory, no Java backend calls)."""

import pytest

from app.core.plugin.loader import PluginDescriptor
from app.core.plugin.manifest import compute_manifest_hash
from app.core.plugin.registry import (
    clear_registry,
    disable_plugin,
    enable_plugin,
    get_plugin,
    get_plugin_by_name,
    list_all_tool_specs,
    list_plugins,
    register_plugin,
    unregister_plugin,
    verify_manifest_integrity,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure clean registry for each test."""
    clear_registry()
    yield
    clear_registry()


def _make_descriptor(name="test_plugin", version="1.0.0", tools=None):
    """Create a test PluginDescriptor."""
    manifest = {"name": name, "version": version, "description": "test"}
    return PluginDescriptor(
        plugin_id=f"{name}@{version}",
        name=name,
        version=version,
        manifest=manifest,
        manifest_hash=compute_manifest_hash(manifest),
        archive_path="/tmp/test.whl",
        archive_hash="abc123",
        extract_dir="/tmp/test_extract",
        tool_specs=tools or [{"name": f"{name}_tool", "description": "test tool"}],
        sandbox_config=None,
    )


# ── Register / Unregister ────────────────────────────────────────────

class TestRegistryLifecycle:
    def test_register_plugin(self):
        desc = _make_descriptor()
        plugin = register_plugin(desc)
        assert plugin.plugin_id == "test_plugin@1.0.0"
        assert plugin.name == "test_plugin"
        assert plugin.enabled is True

    def test_register_plugin_adds_to_list(self):
        desc = _make_descriptor()
        register_plugin(desc)
        plugins = list_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "test_plugin"

    def test_unregister_plugin(self):
        desc = _make_descriptor()
        register_plugin(desc)
        result = unregister_plugin("test_plugin@1.0.0")
        assert result is True
        assert get_plugin("test_plugin@1.0.0") is None

    def test_unregister_nonexistent_returns_false(self):
        result = unregister_plugin("nonexistent")
        assert result is False

    def test_clear_registry(self):
        register_plugin(_make_descriptor("p1"))
        register_plugin(_make_descriptor("p2"))
        count = clear_registry()
        assert count == 2
        assert list_plugins() == []


# ── Lookup ───────────────────────────────────────────────────────────

class TestRegistryLookup:
    def test_get_plugin_by_id(self):
        desc = _make_descriptor()
        register_plugin(desc)
        found = get_plugin("test_plugin@1.0.0")
        assert found is not None
        assert found.name == "test_plugin"

    def test_get_plugin_by_name(self):
        desc = _make_descriptor()
        register_plugin(desc)
        found = get_plugin_by_name("test_plugin")
        assert found is not None
        assert found.version == "1.0.0"

    def test_get_nonexistent_returns_none(self):
        assert get_plugin("nonexistent") is None
        assert get_plugin_by_name("nonexistent") is None


# ── Enable / Disable ────────────────────────────────────────────────

class TestRegistryEnableDisable:
    def test_disable_plugin(self):
        desc = _make_descriptor()
        register_plugin(desc)
        result = disable_plugin("test_plugin@1.0.0")
        assert result is True
        plugin = get_plugin("test_plugin@1.0.0")
        assert plugin.enabled is False

    def test_enable_plugin(self):
        desc = _make_descriptor()
        register_plugin(desc)
        disable_plugin("test_plugin@1.0.0")
        result = enable_plugin("test_plugin@1.0.0")
        assert result is True
        plugin = get_plugin("test_plugin@1.0.0")
        assert plugin.enabled is True

    def test_list_plugins_enabled_only(self):
        d1 = _make_descriptor("p1")
        d2 = _make_descriptor("p2")
        register_plugin(d1)
        register_plugin(d2)
        disable_plugin("p1@1.0.0")

        all_plugins = list_plugins(enabled_only=False)
        assert len(all_plugins) == 2

        enabled_only = list_plugins(enabled_only=True)
        assert len(enabled_only) == 1
        assert enabled_only[0].name == "p2"

    def test_disable_nonexistent_returns_false(self):
        assert disable_plugin("nonexistent") is False

    def test_enable_nonexistent_returns_false(self):
        assert enable_plugin("nonexistent") is False


# ── Tool specs ───────────────────────────────────────────────────────

class TestRegistryToolSpecs:
    def test_list_all_tool_specs(self):
        tools = [{"name": "tool_a", "description": "A"}, {"name": "tool_b", "description": "B"}]
        desc = _make_descriptor(tools=tools)
        register_plugin(desc)
        specs = list_all_tool_specs()
        assert len(specs) == 2
        assert specs[0]["name"] == "tool_a"
        assert specs[1]["name"] == "tool_b"

    def test_tool_specs_include_plugin_metadata(self):
        desc = _make_descriptor()
        register_plugin(desc)
        specs = list_all_tool_specs()
        assert specs[0]["_plugin_id"] == "test_plugin@1.0.0"
        assert specs[0]["_plugin_name"] == "test_plugin"

    def test_disabled_plugin_excluded_from_enabled_specs(self):
        desc = _make_descriptor()
        register_plugin(desc)
        disable_plugin("test_plugin@1.0.0")
        specs = list_all_tool_specs(enabled_only=True)
        assert len(specs) == 0

    def test_disabled_plugin_included_when_not_filtering(self):
        desc = _make_descriptor()
        register_plugin(desc)
        disable_plugin("test_plugin@1.0.0")
        specs = list_all_tool_specs(enabled_only=False)
        assert len(specs) == 1


# ── Integrity verification ───────────────────────────────────────────

class TestRegistryIntegrity:
    def test_verify_manifest_integrity(self):
        desc = _make_descriptor()
        register_plugin(desc)
        assert verify_manifest_integrity("test_plugin@1.0.0", desc.manifest_hash) is True

    def test_verify_manifest_integrity_wrong_hash(self):
        desc = _make_descriptor()
        register_plugin(desc)
        assert verify_manifest_integrity("test_plugin@1.0.0", "wrong_hash") is False

    def test_verify_manifest_integrity_nonexistent(self):
        assert verify_manifest_integrity("nonexistent", "hash") is False
