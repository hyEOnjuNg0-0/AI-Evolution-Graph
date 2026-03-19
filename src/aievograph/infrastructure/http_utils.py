"""Shared HTTP retry utility for infrastructure clients."""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 5.0  # seconds; doubles on each attempt


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    max_retries: int = _MAX_RETRIES,
    base_delay: float = _RETRY_BASE_DELAY,
    **kwargs: Any,
) -> httpx.Response:
    """Send an HTTP request with exponential backoff on 429 / 5xx responses.

    Args:
        client: The async HTTP client to use.
        method: HTTP method string, e.g. "GET" or "POST".
        url: Request URL.
        max_retries: Maximum number of attempts before raising RuntimeError.
        base_delay: Base delay in seconds; doubles on each retry attempt.
        **kwargs: Additional arguments forwarded to the httpx request call.

    Returns:
        The successful httpx.Response.

    Raises:
        RuntimeError: If all retry attempts are exhausted.
        httpx.HTTPStatusError: On non-retryable HTTP errors.
    """
    send = getattr(client, method.lower())
    for attempt in range(max_retries):
        resp = await send(url, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else base_delay * (2 ** attempt)
            logger.warning(
                "HTTP %d — waiting %.1fs before retry (attempt %d/%d)",
                resp.status_code, delay, attempt + 1, max_retries,
            )
            await asyncio.sleep(delay)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"Max retries ({max_retries}) exceeded for {method.upper()} {url}")
