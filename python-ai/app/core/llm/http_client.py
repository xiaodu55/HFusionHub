"""Shared HTTP transport for LLM providers (P3).

Rationale
---------
* Connection reuse: a single lazily-created :class:`httpx.AsyncClient` per
  provider is shared across all instances, so repeated calls reuse TCP/TLS
  connections (httpx keeps a per-host keepalive pool) instead of opening a
  fresh connection per request.
* Bounded retry: transient upstream failures (429 rate-limit, 5xx) and
  connection/timeout errors are retried with exponential backoff + jitter.
  4xx client errors are surfaced immediately so the caller-side friendly
  error mapping sees the original status/message.

The client is created lazily from inside the running event loop (there is no
``await`` between the existence check and the assignment, so concurrent first
calls cannot create duplicates), and closed once at shutdown via
:func:`aclose_shared_clients`.
"""

import asyncio
import logging
import random
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# HTTP statuses worth retrying: rate limiting plus all 5xx server errors.
RETRYABLE_STATUS_CODES = frozenset({429, *range(500, 600)})

# Generous upper bounds for the shared connection pools; httpx only opens
# connections for hosts actually in use, so these are not eagerly allocated.
_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)

# One shared client per owner (e.g. "deepseek" / "ollama") so pools and
# defaults are not mixed across providers.
_shared_clients: Dict[str, httpx.AsyncClient] = {}


def get_shared_client(owner: str = "llm", timeout: float = 120.0) -> httpx.AsyncClient:
    """Return the module-wide shared ``AsyncClient`` for ``owner``.

    The client is created on first use. ``timeout`` only seeds the client's
    default; per-call timeouts (including per-instance overrides from
    ``user_model_config``) are passed explicitly by the caller.
    """
    client = _shared_clients.get(owner)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout), limits=_LIMITS)
        _shared_clients[owner] = client
    return client


async def aclose_shared_clients() -> None:
    """Close all shared clients. Idempotent; safe to call at shutdown."""
    for owner, client in list(_shared_clients.items()):
        if not client.is_closed:
            await client.aclose()
        _shared_clients.pop(owner, None)


async def _sleep_backoff(backoff: float, attempt: int) -> None:
    # Full jitter keeps a fleet of retrying workers from stampeding the
    # upstream at identical instants.
    delay = backoff * (2 ** attempt) + random.uniform(0.0, backoff)
    await asyncio.sleep(delay)


async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    json: Optional[dict] = None,
    timeout: float = 120.0,
    max_retries: int = 3,
    backoff: float = 0.5,
) -> httpx.Response:
    """POST ``url`` retrying transient failures with exponential backoff.

    ``max_retries`` is the number of *additional* attempts after the first
    call (total attempts = ``max_retries + 1``). On a connection/timeout error
    the original ``httpx`` exception is re-raised after the final attempt; on
    a retryable HTTP status the final response is returned so the caller can
    raise its own provider-specific error with the upstream message intact.
    """
    for attempt in range(max_retries + 1):
        try:
            response = await client.post(url, headers=headers, json=json, timeout=timeout)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt == max_retries:
                logger.warning(
                    "LLM POST %s failed after %d attempt(s): %s",
                    url, attempt + 1, exc,
                )
                raise
            logger.debug("LLM POST %s failed (attempt %d/%d): %s", url, attempt + 1, max_retries, exc)
            await _sleep_backoff(backoff, attempt)
            continue

        if response.status_code not in RETRYABLE_STATUS_CODES:
            return response
        if attempt == max_retries:
            return response  # caller surfaces the upstream error as-is
        logger.debug(
            "LLM POST %s got retryable status %d (attempt %d/%d)",
            url, response.status_code, attempt + 1, max_retries,
        )
        await _sleep_backoff(backoff, attempt)

    # Unreachable: the final attempt always returns or raises above.
    raise RuntimeError(f"Unreachable: retry loop for {url} did not terminate")


__all__ = [
    "RETRYABLE_STATUS_CODES",
    "get_shared_client",
    "aclose_shared_clients",
    "post_with_retry",
]
