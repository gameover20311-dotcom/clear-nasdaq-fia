"""Forward-OOS storage guard.

The immutable file ledger remains authoritative, but a Free Render filesystem is
not durable across redeploys. When production is configured with PostgreSQL we
therefore refuse to append/resolve scientific events while the durable mirror is
unavailable. A missed forecast stays missed; this module never backfills it.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

UTC = timezone.utc


def _parse_utc(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def durability_guard_status(root: Path) -> Dict[str, Any]:
    from .forward_oos_durable import durability_status

    status = dict(durability_status(root) or {})
    configured = bool(str(os.getenv("DATABASE_URL", "") or "").strip())
    required_env = str(os.getenv("FIA_FORWARD_OOS_DURABLE_REQUIRED", "1") or "1").strip().lower()
    required = configured and required_env not in {"0", "false", "no", "off"}

    expires_raw = str(os.getenv("FIA_FORWARD_OOS_DURABLE_EXPIRES_AT", "") or "").strip()
    expires = _parse_utc(expires_raw)
    days_remaining = None
    expired = False
    warning = None
    if expires is not None:
        delta = expires - datetime.now(UTC)
        days_remaining = round(delta.total_seconds() / 86400.0, 3)
        expired = delta.total_seconds() <= 0
        if expired:
            warning = "DURABLE_STORE_EXPIRY_REACHED"
        elif delta.total_seconds() <= 7 * 86400:
            warning = "DURABLE_STORE_EXPIRES_WITHIN_7_DAYS"
        elif delta.total_seconds() <= 30 * 86400:
            warning = "DURABLE_STORE_EXPIRES_WITHIN_30_DAYS"

    status.update({
        "configured": configured,
        "required_for_scientific_append": required,
        "expires_at_utc": expires.isoformat() if expires is not None else None,
        "days_remaining": days_remaining,
        "expired": expired,
        "expiry_warning": warning,
    })
    status["append_allowed"] = (not required) or (bool(status.get("durable")) and not expired)
    return status


def require_durable_before_scientific_write(root: Path) -> Dict[str, Any]:
    """Return status; caller must abort when ``append_allowed`` is false."""
    return durability_guard_status(root)
