"""Durable one-time execution-token consumption.

After a human approves a tool call, Java issues a UUID ``execution_token`` in
MySQL (``agent_approval``) and includes it in the approve/decide callback.
Python MUST consume that token through the Java internal endpoint BEFORE the
approved tool may execute.  Consumption is atomic in MySQL — exactly one
replica/attempt succeeds, all others are rejected.

Security contract (fail-closed):
  * token missing         → rejected (no execution)
  * Java unreachable      → rejected (no execution)
  * non-200               → rejected
  * ``consumed=false``    → already used / revoked / wrong token → rejected

The old in-process scoped grant remains as a *cache* layer only; the DB token
is the single source of truth for one-time execution authorization.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.utils.config import config

logger = logging.getLogger(__name__)


class ExecutionTokenError(Exception):
    """Raised when a token cannot be consumed (fail-closed)."""


async def consume_execution_token(
    approval_id,
    execution_token,
    *,
    http_client=None,
    backend_url: Optional[str] = None,
) -> bool:
    """Consume an execution token at the Java backend.  Fail-closed.

    Returns True only when the Java backend confirms the token was consumed
    for this approval_id.  Any failure (network, non-200, consumed=false)
    returns False — the caller must NOT execute the approved tool.
    """
    token = str(execution_token or "").strip()
    if not token:
        logger.warning("Execution-token consume skipped: token is empty")
        return False

    url = f"{backend_url or config.JAVA_BACKEND_URL}/api/internal/agent/approvals/consume"
    payload = {
        "approval_id": str(approval_id),
        "execution_token": token,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Token": config.INTERNAL_API_TOKEN or "",
    }

    try:
        if http_client is not None:
            resp = await http_client.post(url, json=payload, headers=headers, timeout=5.0)
        else:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, headers=headers, timeout=5.0)

        if resp.status_code != 200:
            logger.error(
                "Execution-token consume failed: approval=%s status=%d",
                payload["approval_id"], resp.status_code,
            )
            return False

        data = resp.json()
        # Java internal endpoints wrap results in the unified R<T> envelope:
        # {"code":200,"message":"success","data":{"consumed":true},...}.
        # Python must read the nested `data.consumed`, not the top level.
        envelope = data if isinstance(data, dict) else {}
        consumed = bool(
            isinstance(envelope.get("data"), dict)
            and envelope["data"].get("consumed") is True
        )
        if not consumed:
            logger.warning(
                "Execution-token consume rejected: approval=%s token=%s... body=%s",
                payload["approval_id"], token[:8],
                _safe_summary(envelope),
            )
        return consumed

    except Exception as e:
        logger.error(
            "Execution-token consume error (fail-closed): approval=%s err=%s",
            payload["approval_id"], e,
        )
        return False


def _safe_summary(envelope: dict) -> str:
    """Short, non-secret summary of the consume response for logging."""
    try:
        code = envelope.get("code")
        message = str(envelope.get("message", ""))[:80]
        return f"code={code} message={message!r}"
    except Exception:
        return "unparseable body"