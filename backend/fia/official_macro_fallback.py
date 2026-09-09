"""Official-source macro release calendar fallback.

This module exists because a vendor economic-calendar endpoint can be unavailable
on some account tiers.  Calendar truth must not disappear merely because a
premium endpoint is unavailable.

Sources (all public, official):
- BLS online release calendar (ICS): CPI and Employment Situation dates.
- BEA release schedule: GDP and Personal Income and Outlays (PCE) dates.
- Federal Reserve FOMC calendar: next policy-decision date.

Important: an official release *schedule* is not a point-in-time consensus feed.
This module therefore never manufactures a directional macro score.  If the
vendor path supplies a released event with actual + timestamped consensus, that
pre-existing score is preserved.  Otherwise macro remains None while calendar
risk is reported as available evidence.
"""
from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
BLS_ICS = "https://www.bls.gov/schedule/news_release/bls.ics"
BEA_SCHEDULE = "https://www.bea.gov/news/schedule/full"


async def _get_text(url: str, timeout: float = 15.0) -> Optional[str]:
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "CLEAR-NASDAQ-FIA/1.0 research-calendar",
                "Accept": "text/html,text/calendar,text/plain,*/*",
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception:
        return None


def _unfold_ics(text: str) -> List[str]:
    lines: List[str] = []
    for raw in str(text or "").replace("\r\n", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw.rstrip("\r"))
    return lines


def _parse_ics_dt(line: str) -> Optional[datetime]:
    if ":" not in line:
        return None
    head, value = line.split(":", 1)
    value = value.strip()
    try:
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            return dt
        if "T" in value:
            fmt = "%Y%m%dT%H%M%S" if len(value) >= 15 else "%Y%m%dT%H%M"
            dt = datetime.strptime(value[:15] if fmt.endswith("%S") else value[:13], fmt)
        else:
            dt = datetime.strptime(value[:8], "%Y%m%d")
        # BLS schedule times are Eastern Time. Respect an explicit UTC marker
        # above; otherwise use America/New_York so DST is handled correctly.
        return dt.replace(tzinfo=NY).astimezone(UTC)
    except (ValueError, TypeError):
        return None


def parse_bls_ics(text: str, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    horizon = now + timedelta(days=60)
    blocks: List[List[str]] = []
    current: Optional[List[str]] = None
    for line in _unfold_ics(text):
        if line == "BEGIN:VEVENT":
            current = []
        elif line == "END:VEVENT":
            if current is not None:
                blocks.append(current)
            current = None
        elif current is not None:
            current.append(line)

    events: List[Dict[str, Any]] = []
    for block in blocks:
        summary = ""
        dt = None
        for line in block:
            if line.startswith("SUMMARY") and ":" in line:
                summary = html.unescape(line.split(":", 1)[1].strip())
            elif line.startswith("DTSTART"):
                dt = _parse_ics_dt(line)
        lower = summary.lower()
        kind = None
        if "consumer price index" in lower:
            kind = "CPI"
        elif "employment situation" in lower:
            # One release contains both payrolls and unemployment. We retain the
            # official event name rather than pretending it is only one statistic.
            kind = "EMPLOYMENT_SITUATION"
        if not kind or dt is None:
            continue
        if dt < now - timedelta(days=1) or dt > horizon:
            continue
        events.append({
            "type": kind,
            "name": summary,
            "time_utc": dt.isoformat(),
            "source": "U.S. Bureau of Labor Statistics release calendar",
            "source_contract": "BLS_ICS",
            "actual": None,
            "expected": None,
            "directional_score_available": False,
        })
    return sorted(events, key=lambda x: x["time_utc"])


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            value = " ".join(str(data).split())
            if value:
                self._cell.append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None:
            if self._row is not None:
                self._row.append(" ".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
            self._cell = None


_MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2})\s+(\d{1,2}):(\d{2})\s*(AM|PM)\b",
    re.I,
)


def _bea_kind(title: str) -> Optional[str]:
    lower = str(title or "").lower()
    if "personal income and outlays" in lower:
        return "PCE"
    if "gross domestic product" in lower or re.search(r"\bgdp\b", lower):
        return "GDP"
    return None


def parse_bea_schedule(text: str, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    horizon = now + timedelta(days=90)
    parser = _TableParser()
    try:
        parser.feed(str(text or ""))
    except Exception:
        return []

    events: List[Dict[str, Any]] = []
    for row in parser.rows:
        joined = " | ".join(row)
        m = _DATE_RE.search(joined)
        if not m:
            continue
        title = ""
        # Usually the release title is the longest non-date cell. This is more
        # robust to BEA adding a small News/Data type column.
        candidates = [c for c in row if not _DATE_RE.search(c) and c.lower() not in {"news", "data", "view"}]
        if candidates:
            title = max(candidates, key=len)
        kind = _bea_kind(title)
        if not kind:
            continue

        month = _MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        hour = int(m.group(3))
        minute = int(m.group(4))
        ampm = m.group(5).upper()
        if ampm == "PM" and hour != 12:
            hour += 12
        if ampm == "AM" and hour == 12:
            hour = 0
        year = now.astimezone(NY).year
        try:
            local = datetime(year, month, day, hour, minute, tzinfo=NY)
        except ValueError:
            continue
        dt = local.astimezone(UTC)
        if dt < now - timedelta(days=1) or dt > horizon:
            continue
        events.append({
            "type": kind,
            "name": title,
            "time_utc": dt.isoformat(),
            "source": "U.S. Bureau of Economic Analysis release schedule",
            "source_contract": "BEA_PUBLIC_HTML_TABLE",
            "actual": None,
            "expected": None,
            "directional_score_available": False,
        })
    return sorted(events, key=lambda x: x["time_utc"])


async def _fomc_event(now: datetime) -> Optional[Dict[str, Any]]:
    try:
        from .fed_evidence import _fomc_calendar
        result = await _fomc_calendar(None, now=now)
    except Exception:
        return None
    date = (result or {}).get("next_meeting_date")
    if not date:
        return None
    # The official page gives the decision date. We intentionally do NOT invent
    # an intraday release time when the parser did not retrieve one.
    return {
        "type": "FOMC",
        "name": "Federal Open Market Committee decision date",
        "date_et": date,
        "time_utc": None,
        "source": "Federal Reserve FOMC meeting calendar",
        "source_contract": str((result or {}).get("contract") or "OFFICIAL_CALENDAR"),
        "actual": None,
        "expected": None,
        "directional_score_available": False,
    }


async def build_official_macro_calendar(now: Optional[datetime] = None) -> Dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    bls_text, bea_text, fomc = await asyncio.gather(
        _get_text(BLS_ICS),
        _get_text(BEA_SCHEDULE),
        _fomc_event(now),
    )
    bls = parse_bls_ics(bls_text or "", now=now) if bls_text else []
    bea = parse_bea_schedule(bea_text or "", now=now) if bea_text else []
    events = bls + bea + ([fomc] if fomc else [])

    def key(item: Dict[str, Any]):
        return (
            str(item.get("time_utc") or item.get("date_et") or ""),
            str(item.get("type") or ""),
            str(item.get("name") or ""),
        )

    dedup: Dict[tuple, Dict[str, Any]] = {}
    for item in events:
        dedup[key(item)] = item
    events = sorted(dedup.values(), key=lambda x: str(x.get("time_utc") or x.get("date_et") or ""))
    states = {
        "BLS": "LIVE" if bls_text and bls else ("FETCHED_NO_TRACKED_EVENTS" if bls_text else "SOURCE_FAILURE"),
        "BEA": "LIVE" if bea_text and bea else ("FETCHED_NO_TRACKED_EVENTS" if bea_text else "SOURCE_FAILURE"),
        "FED": "LIVE" if fomc else "SOURCE_FAILURE",
    }
    return {
        "available": any(v in {"LIVE", "FETCHED_NO_TRACKED_EVENTS"} for v in states.values()),
        "checked_at_utc": now.isoformat(),
        "events": events[:40],
        "event_count": len(events),
        "source_states": states,
        "sources": [
            "U.S. Bureau of Labor Statistics",
            "U.S. Bureau of Economic Analysis",
            "Federal Reserve",
        ],
        "consensus_available": False,
        "directional_score": None,
        "policy": "Official schedule only; no fake consensus and no fake directional zero.",
    }


def install() -> None:
    """Wrap the vendor macro path with official-source schedule fallback."""
    from . import live_market_truth as target

    if getattr(target, "_official_macro_fallback_installed", False):
        return
    original = target._macro_calendar

    async def macro_calendar_with_official(hub: Any) -> Dict[str, Any]:
        vendor = await original(hub)
        official = await build_official_macro_calendar()
        if not isinstance(vendor, dict):
            vendor = {}

        # Keep a genuine released actual-vs-consensus directional score if the
        # vendor supplied one. Official schedules only supplement provenance.
        result = dict(vendor)
        result["macro_official_calendar"] = official
        if official.get("available"):
            vendor_events = list(result.get("macro_calendar_events") or [])
            official_events = list(official.get("events") or [])
            merged: Dict[tuple, Dict[str, Any]] = {}
            for item in vendor_events + official_events:
                if not isinstance(item, dict):
                    continue
                k = (
                    str(item.get("time_utc") or item.get("date_et") or ""),
                    str(item.get("type") or ""),
                    str(item.get("name") or ""),
                )
                merged[k] = item
            result["macro_calendar_events"] = list(merged.values())[:40]
            result["macro_calendar_event_count"] = len(merged)
            result["macro_calendar_available"] = True
            result["macro_calendar_checked_at_utc"] = official.get("checked_at_utc")
            result["macro_calendar_source"] = "BLS + BEA + Federal Reserve official calendars"
            result["macro_calendar_source_states"] = official.get("source_states")
            if result.get("macro") is None:
                result["macro_status"] = "official_calendar_live_no_point_in_time_consensus"
        return result

    target._macro_calendar = macro_calendar_with_official
    target._official_macro_fallback_installed = True
