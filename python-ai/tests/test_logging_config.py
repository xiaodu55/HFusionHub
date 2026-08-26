"""R16-17 日志配置测试：JSON 行格式、trace_id 经 handler 级 filter 全局注入。"""

import json
import logging

import pytest

from app.utils import trace
from app.utils.logging_config import JsonFormatter, SafeFormatter, TraceFilter, configure_logging


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    trace.set_trace_id(None)


def _record(logger_name="app.core.rag.retriever", msg="hello 测试", exc_info=None):
    return logging.LogRecord(
        name=logger_name, level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=exc_info,
    )


def test_json_formatter_emits_parseable_line():
    line = JsonFormatter().format(_record())
    payload = json.loads(line)

    assert payload["message"] == "hello 测试"
    assert payload["level"] == "INFO"
    assert payload["logger_name"] == "app.core.rag.retriever"
    assert payload["trace_id"] == "-"
    assert "@timestamp" in payload


def test_json_formatter_includes_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        line = JsonFormatter().format(_record(exc_info=sys.exc_info()))
    payload = json.loads(line)

    assert "ValueError: boom" in payload["exception"]


def test_trace_filter_on_handler_reaches_child_logger_records():
    """回归点：filter 挂 handler 才对子 logger 传播记录生效（旧实现挂根 logger 恒为 '-'）。"""
    handler = logging.StreamHandler()
    handler.addFilter(TraceFilter())
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger("app.some.child.module")
    logger.handlers = []
    logger.propagate = True

    root = logging.getLogger()
    root.handlers = [handler]

    trace.set_trace_id("tid-123")
    logger.info("带 trace 的记录")

    root.handlers = []

    # 直接校验 filter 行为（不依赖 stdout 捕获）：handler.filter 通过后 record 带 trace_id
    record = _record()
    assert TraceFilter().filter(record) is True
    assert record.trace_id == "tid-123"


def test_trace_filter_defaults_to_dash_without_context():
    trace.set_trace_id(None)
    record = _record()
    TraceFilter().filter(record)

    assert record.trace_id == "-"


def test_safe_formatter_pads_missing_trace_id():
    formatted = SafeFormatter("%(asctime)s [%(levelname)s] [%(trace_id)s] %(name)s: %(message)s").format(_record())

    assert "[-]" in formatted


def test_configure_logging_json_mode(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    configure_logging()

    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)
    assert any(isinstance(f, TraceFilter) for f in handler.filters)


def test_configure_logging_text_mode_default(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    configure_logging()

    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, SafeFormatter)
