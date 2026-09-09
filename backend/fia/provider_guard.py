"""Runtime guard for outbound data-provider requests.

This module changes transport behaviour only. It does not change provider
priority, fallback semantics, market scoring, calibration, or missing-data
handling. Repeated 403/429/5xx/timeouts are cooled down so a degraded vendor
cannot create a quota/latency/memory stampede.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx


def _safe_parts(url: str) -> tuple[str, str]:
    try:
        p = urlsplit(str(url))
        host = p.netloc or "unknown"
        safe = f"{p.scheme}://{host}{p.path}"
        return host, safe
    except Exception:
        return "unknown", "<provider-url-redacted>"


def _retry_after_seconds(response: Any) -> float:
    try:
        raw = response.headers.get("retry-after")
        if raw is not None:
            return max(30.0, min(900.0, float(raw)))
    except Exception:
        pass
    return 120.0


async def guarded_get(
    self: Any,
    url: str,
    params: Optional[dict] = None,
    timeout: float = 10,
    headers: Optional[dict] = None,
):
    """Drop-in replacement for ``ProviderHub.get`` with fail-soft throttling."""
    host, safe_url = _safe_parts(url)
    path_key = safe_url
    now = time.monotonic()

    state = getattr(self, "_a2z_provider_guard", None)
    if state is None:
        limit = max(2, min(16, int(os.getenv("FIA_PROVIDER_MAX_CONCURRENCY", "6") or "6")))
        state = {
            "semaphore": asyncio.Semaphore(limit),
            "path_cooldown": {},
            "host_cooldown": {},
        }
        setattr(self, "_a2z_provider_guard", state)

    if float(state["host_cooldown"].get(host, 0.0) or 0.0) > now:
        return None
    if float(state["path_cooldown"].get(path_key, 0.0) or 0.0) > now:
        return None

    async with state["semaphore"]:
        # Re-check after waiting on the semaphore; another request may have
        # tripped a cooldown while this coroutine was queued.
        now = time.monotonic()
        if float(state["host_cooldown"].get(host, 0.0) or 0.0) > now:
            return None
        if float(state["path_cooldown"].get(path_key, 0.0) or 0.0) > now:
            return None

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                state["path_cooldown"].pop(path_key, None)
                return response.json()
        except Exception as exc:
            status = None
            response = getattr(exc, "response", None)
            if isinstance(exc, httpx.HTTPStatusError) and response is not None:
                status = getattr(response, "status_code", None)

            now = time.monotonic()
            if status == 403:
                # Endpoint/account-tier denial: do not hammer it every snapshot.
                state["path_cooldown"][path_key] = now + 900.0
            elif status == 429:
                # Rate limits are normally provider-wide, so cool the host.
                state["host_cooldown"][host] = now + _retry_after_seconds(response)
            elif status is not None and int(status) >= 500:
                state["path_cooldown"][path_key] = now + 20.0
            elif isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
                state["path_cooldown"][path_key] = now + 10.0

            # Never stringify the exception: request URLs can contain API keys.
            if status is not None:
                print(f"Provider error: {safe_url} -> HTTP {status} ({type(exc).__name__})")
            else:
                print(f"Provider error: {safe_url} -> {type(exc).__name__}")
            return None


def install() -> None:
    """Install exactly once without importing any network data."""
    from .providers import ProviderHub

    if getattr(ProviderHub, "_a2z_provider_guard_installed", False):
        return
    ProviderHub.get = guarded_get
    ProviderHub._a2z_provider_guard_installed = True
