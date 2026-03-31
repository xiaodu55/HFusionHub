"""Tests for the distributed trace context (contextvars)."""

from __future__ import annotations

import asyncio
import pytest

from app.utils.trace import (
    HEADER_NAME,
    clear_trace_id,
    create_trace_id,
    get_trace_id,
    set_trace_id,
)


class TestTraceContext:
    """Unit tests for the trace contextvars module."""

    def setup_method(self):
        clear_trace_id()

    def test_get_trace_id_returns_none_when_not_set(self):
        assert get_trace_id() is None

    def test_set_and_get_trace_id(self):
        set_trace_id("my-trace-001")
        assert get_trace_id() == "my-trace-001"

    def test_create_trace_id_generates_uuid(self):
        tid = create_trace_id()
        assert tid is not None
        assert len(tid) == 32  # UUID hex without dashes
        assert "-" not in tid
        assert get_trace_id() == tid

    def test_create_trace_id_overwrites_existing(self):
        set_trace_id("old-id")
        new_id = create_trace_id()
        assert new_id != "old-id"
        assert get_trace_id() == new_id

    def test_clear_trace_id(self):
        set_trace_id("to-clear")
        assert get_trace_id() == "to-clear"
        clear_trace_id()
        assert get_trace_id() is None

    def test_header_name_constant(self):
        assert HEADER_NAME == "X-Trace-ID"

    @pytest.mark.asyncio
    async def test_concurrent_requests_isolated(self):
        """Two concurrent async tasks must NOT see each other's trace_id."""
        results = {}

        async def worker(task_id: str):
            set_trace_id(f"trace-{task_id}")
            # Simulate some async work
            await asyncio.sleep(0.01)
            results[task_id] = get_trace_id()
            clear_trace_id()

        await asyncio.gather(
            worker("aaa"),
            worker("bbb"),
            worker("ccc"),
        )

        assert results["aaa"] == "trace-aaa"
        assert results["bbb"] == "trace-bbb"
        assert results["ccc"] == "trace-ccc"

    @pytest.mark.asyncio
    async def test_concurrent_requests_no_leak_after_clear(self):
        """After clear, a new task must NOT see a stale trace_id from another."""
        async def set_and_clear():
            set_trace_id("temp-id")
            await asyncio.sleep(0.01)
            clear_trace_id()

        await set_and_clear()
        # A fresh task should see None, not "temp-id"
        assert get_trace_id() is None

    def test_set_trace_id_with_empty_string(self):
        set_trace_id("")
        # Empty string is still a valid value (middleware should guard, but context allows it)
        assert get_trace_id() == ""

    def test_set_trace_id_with_long_value(self):
        long_id = "x" * 10000
        set_trace_id(long_id)
        assert get_trace_id() == long_id
