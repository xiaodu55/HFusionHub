"""Tests for the platform built-in plugin wheels loader (P2-3).

Verifies:
  - Loads wheels from the configured dir when each has a matching .sha256 sidecar
  - Refuses wheels whose sidecar is missing or malformed (supply-chain gate)
  - Is idempotent / returns empty for missing dir (never crashes startup)
  - Derives plugin_id correctly from wheel filenames
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.plugin.builtins import (
    _plugin_id_from_wheel,
    load_builtin_wheels,
)


class _FakeRegistered:
    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id


def _write_wheel(tmp_path, name: str, digest: str | None = None) -> None:
    wheel = tmp_path / name
    wheel.write_bytes(b"PK\x03\x04 fake wheel")
    if digest is not None:
        (tmp_path / f"{name}.sha256").write_text(digest + "\n", encoding="utf-8")


def test_plugin_id_from_wheel():
    assert _plugin_id_from_wheel("bid_docx-1.0.0-py3-none-any.whl") == "bid_docx@1.0.0"
    assert _plugin_id_from_wheel("bid_quote-1.0.0-py3-none-any.whl") == "bid_quote@1.0.0"
    assert _plugin_id_from_wheel("weird.whl") is None


def test_loads_wheels_with_valid_sidecar(tmp_path, monkeypatch):
    digest = "a" * 64
    _write_wheel(tmp_path, "bid_docx-1.0.0-py3-none-any.whl", digest)
    _write_wheel(tmp_path, "bid_quote-1.0.0-py3-none-any.whl", digest)

    fake = MagicMock()
    fake.side_effect = lambda wheel_path, plugin_id, expected_hash: _FakeRegistered(plugin_id)
    with patch("app.core.plugin.registry.load_and_register_wheel", fake) as loader:
        loaded = load_builtin_wheels(str(tmp_path))

    assert set(loaded) == {"bid_docx@1.0.0", "bid_quote@1.0.0"}
    assert loader.call_count == 2
    assert loader.call_args.kwargs["expected_hash"] == digest


def test_skips_wheel_without_sidecar(tmp_path):
    _write_wheel(tmp_path, "bid_docx-1.0.0-py3-none-any.whl", digest=None)

    fake = MagicMock()
    with patch("app.core.plugin.registry.load_and_register_wheel", fake):
        loaded = load_builtin_wheels(str(tmp_path))

    assert loaded == []
    fake.assert_not_called()


def test_skips_wheel_with_malformed_sidecar(tmp_path):
    _write_wheel(tmp_path, "bid_docx-1.0.0-py3-none-any.whl", digest="not-a-hex-digest")

    fake = MagicMock()
    with patch("app.core.plugin.registry.load_and_register_wheel", fake):
        loaded = load_builtin_wheels(str(tmp_path))

    assert loaded == []
    fake.assert_not_called()


def test_missing_dir_is_idempotent():
    fake = MagicMock()
    with patch("app.core.plugin.registry.load_and_register_wheel", fake):
        assert load_builtin_wheels("/nonexistent/plugin/wheels") == []
    fake.assert_not_called()


def test_single_failure_does_not_block_others(tmp_path):
    digest = "b" * 64
    _write_wheel(tmp_path, "bid_docx-1.0.0-py3-none-any.whl", digest)
    _write_wheel(tmp_path, "bid_quote-1.0.0-py3-none-any.whl", digest)

    fake = MagicMock()
    fake.side_effect = [
        RuntimeError("boom"),  # 第一个加载失败
        _FakeRegistered("bid_quote@1.0.0"),
    ]
    with patch("app.core.plugin.registry.load_and_register_wheel", fake):
        loaded = load_builtin_wheels(str(tmp_path))

    assert loaded == ["bid_quote@1.0.0"]
