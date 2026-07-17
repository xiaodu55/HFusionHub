"""Fail-closed client for Java's plugin-execution usage ledger."""

from __future__ import annotations

import asyncio
import logging

from app.utils.config import config

logger = logging.getLogger(__name__)
_OPERATIONS = {"reserve", "settle", "release"}


async def transition_plugin_execution(
    operation: str,
    *,
    tenant_id: int,
    user_id: int,
    execution_id: str,
    plugin_id: str,
    tool_name: str,
    http_client=None,
    backend_url: str | None = None,
) -> bool:
    """Apply one idempotent plugin-usage transition through Java."""
    normalized = str(operation or "").lower()
    if normalized not in _OPERATIONS or min(tenant_id, user_id) < 1 or not all(
        [execution_id, plugin_id, tool_name, config.INTERNAL_API_TOKEN]
    ):
        logger.error("Plugin quota transition rejected locally: operation=%s execution=%s", normalized, execution_id)
        return False

    url = f"{backend_url or config.JAVA_BACKEND_URL}/api/internal/plugin/executions/quota"
    payload = {
        "operation": normalized.upper(), "tenant_id": tenant_id, "user_id": user_id,
        "execution_id": execution_id, "plugin_id": plugin_id, "tool_name": tool_name,
    }
    headers = {"Content-Type": "application/json", "X-Internal-Token": config.INTERNAL_API_TOKEN}

    for attempt in range(3):
        try:
            if http_client is not None:
                response = await http_client.post(url, json=payload, headers=headers, timeout=5.0)
            else:
                from app.core.llm.http_client import get_shared_client
                client = get_shared_client("plugin-quota", timeout=5.0)
                response = await client.post(url, json=payload, headers=headers, timeout=5.0)
            envelope = response.json() if response.status_code == 200 else {}
            if (
                response.status_code == 200 and isinstance(envelope, dict)
                and envelope.get("code") == 200 and isinstance(envelope.get("data"), dict)
                and envelope["data"].get("operation") == normalized
                and envelope["data"].get("execution_id") == execution_id
            ):
                return True
            logger.warning("Plugin quota transition rejected: operation=%s execution=%s status=%s",
                           normalized, execution_id, response.status_code)
            return False
        except Exception as exc:
            if attempt == 2:
                logger.error("Plugin quota transition unavailable (fail-closed): operation=%s execution=%s err=%s",
                             normalized, execution_id, exc)
                return False
            await asyncio.sleep(0.1 * (attempt + 1))
    return False
