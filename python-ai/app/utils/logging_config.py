"""应用日志配置（R16-17 结构化日志）。

- ``LOG_FORMAT=text``（默认）：人类可读 pattern，含 trace_id；
- ``LOG_FORMAT=json``：每行一条 JSON（Loki/ES 采集就绪），字段
  timestamp/level/logger/message/trace_id，异常时附 exception；
- ``TraceFilter`` 必须挂在 **handler** 上而非根 logger——标准库语义下根
  logger 的 filter 只对"直接经根 logger 发出的记录"生效，app.* 子 logger
  传播上来的记录不经过它，导致 trace_id 恒为 "-"。
"""

from __future__ import annotations

import json
import logging
import os
import sys


class SafeFormatter(logging.Formatter):
    """text 格式：trace_id 缺省占位，避免子 logger 记录格式断裂。"""

    def format(self, record):
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return super().format(record)


class JsonFormatter(logging.Formatter):
    """JSON 行格式：采集侧按行解析即可入 Loki/ES，字段名与 Java 端
    LogstashEncoder 的常用约定对齐（message/level/logger_name/trace_id）。"""

    def format(self, record):
        payload = {
            "@timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger_name": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TraceFilter(logging.Filter):
    """把 contextvars 里的 trace_id 注入每条记录（挂在 handler 上全局生效）。"""

    def filter(self, record):
        from app.utils.trace import get_trace_id

        record.trace_id = get_trace_id() or "-"
        return True


def configure_logging() -> None:
    """按 LOG_FORMAT 初始化根 logger（幂等，应用启动时调用一次）。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(TraceFilter())
    if os.getenv("LOG_FORMAT", "text").strip().lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            SafeFormatter("%(asctime)s [%(levelname)s] [%(trace_id)s] %(name)s: %(message)s")
        )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
