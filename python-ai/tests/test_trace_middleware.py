"""Tests for the TraceMiddleware — verifying X-Trace-ID propagation through FastAPI."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.utils.trace import HEADER_NAME


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def transport(app):
    return ASGITransport(app=app)


class TestTraceMiddleware:
    """Integration tests using FastAPI TestClient (httpx AsyncClient)."""

    @pytest.mark.asyncio
    async def test_generates_trace_id_when_no_header(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert HEADER_NAME in resp.headers
            trace_id = resp.headers[HEADER_NAME]
            assert trace_id is not None
            assert len(trace_id) == 32

    @pytest.mark.asyncio
    async def test_passthrough_existing_trace_id(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/health",
                headers={HEADER_NAME: "my-custom-trace-999"},
            )
            assert resp.headers[HEADER_NAME] == "my-custom-trace-999"

    @pytest.mark.asyncio
    async def test_returns_same_id_in_response_as_sent(self, transport):
        """The trace ID returned in the response must match what was sent."""
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            sent_id = "abcdef1234567890abcdef1234567890"
            resp = await client.get(
                "/health",
                headers={HEADER_NAME: sent_id},
            )
            assert resp.headers[HEADER_NAME] == sent_id

    @pytest.mark.asyncio
    async def test_concurrent_requests_get_different_ids(self, transport):
        """Two parallel requests must not share trace IDs."""
        import asyncio

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async def fetch():
                resp = await client.get("/health")
                return resp.headers[HEADER_NAME]

            results = await asyncio.gather(fetch(), fetch(), fetch())
            # All three should have different IDs
            assert len(set(results)) == 3

    @pytest.mark.asyncio
    async def test_empty_header_triggers_generation(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/health",
                headers={HEADER_NAME: "   "},
            )
            # Blank header should trigger generation, not passthrough
            assert resp.headers[HEADER_NAME] != "   "
            assert len(resp.headers[HEADER_NAME]) == 32

    @pytest.mark.asyncio
    async def test_trace_id_is_32_hex_chars(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            tid = resp.headers[HEADER_NAME]
            assert len(tid) == 32
            int(tid, 16)  # should be valid hex

    @pytest.mark.asyncio
    async def test_health_endpoint_has_trace_id(self, transport):
        """Even the health endpoint should have trace propagation."""
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert HEADER_NAME in resp.headers


class TestOtelTraceparentPropagation:
    """W3C traceparent 提取 → OTel 服务端 span（OTEL 启用时才生效）。"""

    @pytest.mark.asyncio
    async def test_traceparent_creates_child_server_span(self, transport, monkeypatch):
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from app.utils import telemetry as telemetry_mod

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        otel_trace.set_tracer_provider(provider)
        # TraceMiddleware 经 telemetry.is_enabled() 判断是否启用 OTel
        monkeypatch.setattr(telemetry_mod, "_enabled", True)

        remote_trace_id = "1" * 32
        remote_parent_id = "2" * 16
        traceparent = f"00-{remote_trace_id}-{remote_parent_id}-01"
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health", headers={"traceparent": traceparent})
            assert resp.status_code == 200

        spans = exporter.get_finished_spans()
        assert any("GET /health" in s.name for s in spans), \
            f"未创建服务端 span: {[s.name for s in spans]}"
        span = next(s for s in spans if "GET /health" in s.name)
        # 父级 = Java 侧传入的 remote parent——同一 trace id 连成一条调用链
        assert span.context.trace_id == int(remote_trace_id, 16)
        assert span.parent is not None
        assert span.parent.span_id == int(remote_parent_id, 16)

    @pytest.mark.asyncio
    async def test_traceparent_ignored_when_otel_disabled(self, transport, monkeypatch):
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from app.utils import telemetry as telemetry_mod

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        otel_trace.set_tracer_provider(provider)
        monkeypatch.setattr(telemetry_mod, "_enabled", False)

        traceparent = "00-" + "1" * 32 + "-" + "2" * 16 + "-01"
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health", headers={"traceparent": traceparent})
            assert resp.status_code == 200

        assert len(exporter.get_finished_spans()) == 0


class TestTraceIdValidation:
    """客户端提供的 trace ID 会进入日志与响应头——必须做格式校验防注入。"""

    @pytest.mark.asyncio
    async def test_rejects_injection_style_id(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/health",
                headers={HEADER_NAME: "inject me <script>alert(1)</script>"},
            )
            tid = resp.headers[HEADER_NAME]
            assert "<script>" not in tid
            assert len(tid) == 32

    @pytest.mark.asyncio
    async def test_rejects_oversized_id(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health", headers={HEADER_NAME: "a" * 300})
            assert len(resp.headers[HEADER_NAME]) == 32

    @pytest.mark.asyncio
    async def test_accepts_max_length_legal_id(self, transport):
        legal = "A-b_09" * 10 + "x"  # 61 chars, alnum+dash+underscore
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health", headers={HEADER_NAME: legal})
            assert resp.headers[HEADER_NAME] == legal
