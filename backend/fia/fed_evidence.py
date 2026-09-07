"""Zero-cost Federal Reserve EVIDENCE producer. Not a forecast input.

WHAT THIS IS
------------
Three genuinely free, timestamped Fed sources, fetched and reported with honest
provenance so a human reading the dashboard can see the policy backdrop:

  policy_rate      FRED DFEDTARU/DFEDTARL/DFF  -- documented JSON API, stable
                   contract, already keyed in this deployment.
  fomc_calendar    federalreserve.gov/monetarypolicy/fomccalendars.htm
                   -- HTML SCRAPE. Free, but there is no published contract, so
                   it is labelled SCRAPE_NO_STABLE_CONTRACT and fails closed.
  statements       federalreserve.gov/feeds/press_monetary.xml
                   -- a real RSS feed with pubDate timestamps. Structured, free.

WHAT THIS IS EXPLICITLY NOT
---------------------------
* Not scored. Nothing here produces a number that enters a probability.
* Not sentiment. Statement text is reported verbatim with its publication
  timestamp; it is NOT run through a hawkish/dovish scorer, because no evidence
  exists in this project that such a score predicts NQ, and an unproven score
  presented next to a forecast would read as if it did.
* Not a substitute for a macro event calendar (that remains NO_PRODUCER).

PRODUCTION INFLUENCE IS OFF BY CONSTRUCTION
-------------------------------------------
`fia.engine` and `fia.premove_watch` do not import this module, and this module
imports neither of them. `production_influence` is reported as False on every
payload, and test_freeze_parity/test_fed_evidence assert the isolation.

FAIL CLOSED
-----------
Any fetch failure yields an explicit state -- SOURCE_FAILURE, or
NO_PRODUCER_IMPLEMENTED where a source genuinely does not exist. No value is
ever invented, and a stale cache is never presented as current.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FOMC_RSS_URL = "https://www.federalreserve.gov/feeds/press_monetary.xml"

STATE_OK = "RELEASED_VERIFIED"
STATE_FAIL = "SOURCE_FAILURE"
STATE_NO_KEY = "API_KEY_NOT_CONFIGURED"
STATE_EMPTY = "NO_OBSERVATIONS_RETURNED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_text(url: str, timeout: float = 15) -> Optional[str]:
    """Fetch a text/XML/HTML document.

    ProviderHub.get always calls .json(), so it cannot read the Fed's RSS or
    calendar page. This is a local, isolated fetcher: keeping it here means this
    module adds nothing to the shared provider path that a forecast input uses.
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "CLEAR-NASDAQ-FIA/1.0"})
            r.raise_for_status()
            return r.text
    except Exception as exc:                                        # noqa: BLE001
        print("Fed evidence fetch failed: %s -> %s" % (url, exc))
        return None


async def _policy_rate(hub) -> Dict[str, Any]:
    key = (getattr(hub, "keys", {}) or {}).get("FRED_API_KEY") or os.getenv("FRED_API_KEY")
    if not key:
        return {"state": STATE_NO_KEY, "value": None, "series": None,
                "remediation": "Set FRED_API_KEY to enable policy-rate evidence."}
    # DFEDTARU is the upper bound of the current target range -- the number the
    # market actually quotes. DFF (effective rate) is the fallback.
    for series in ("DFEDTARU", "DFF"):
        try:
            r = await hub.get(FRED_BASE, {
                "series_id": series, "api_key": key, "file_type": "json",
                "sort_order": "desc", "limit": 1}, timeout=12)
        except Exception as exc:                                    # noqa: BLE001
            return {"state": STATE_FAIL, "value": None, "series": series,
                    "error": type(exc).__name__}
        obs = (r or {}).get("observations") or []
        if obs and str(obs[0].get("value", ".")) not in (".", "", None):
            try:
                val = float(obs[0]["value"])
            except (TypeError, ValueError):
                continue
            return {"state": STATE_OK, "value": val, "series": series,
                    "observation_date": obs[0].get("date"),
                    "source": "FRED " + series,
                    "contract": "DOCUMENTED_JSON_API",
                    "units": "percent_per_annum"}
    return {"state": STATE_EMPTY, "value": None, "series": None,
            "source": "FRED DFEDTARU/DFF"}


async def _fomc_calendar(hub, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Meeting dates scraped from the Fed's own calendar page.

    Labelled a scrape on purpose: there is no published contract for this page,
    so a layout change must degrade to SOURCE_FAILURE rather than to a wrong date.
    """
    now = now or datetime.now(timezone.utc)
    try:
        html = await _get_text(FOMC_CALENDAR_URL)
    except Exception as exc:                                        # noqa: BLE001
        return {"state": STATE_FAIL, "error": type(exc).__name__,
                "contract": "SCRAPE_NO_STABLE_CONTRACT"}
    if not isinstance(html, str) or len(html) < 2000:
        return {"state": STATE_FAIL,
                "reason": "calendar page did not return parseable HTML",
                "contract": "SCRAPE_NO_STABLE_CONTRACT"}
    # The page lists PAST meetings with a fomcpresconf<YYYYMMDD> anchor, but
    # SCHEDULED meetings have no anchor at all -- only a year panel with month
    # and day-range cells. Parsing anchors alone therefore reported
    # next_meeting_date=None while meetings were in fact scheduled, which is a
    # worse failure than admitting the parse failed. Both forms are parsed, and
    # if the forward panel cannot be read the result says so explicitly.
    past_dates: List[str] = []
    for m in re.finditer(r"fomcpresconf(\d{8})", html):
        d = m.group(1)
        iso = "%s-%s-%s" % (d[0:4], d[4:6], d[6:8])
        if iso not in past_dates:
            past_dates.append(iso)

    scheduled: List[str] = []
    months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
              "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
              "november": 11, "december": 12}
    for panel in re.finditer(
            r'<a id="\d+">(\d{4})\s+FOMC Meetings</a>(.*?)(?=<a id="\d+">\d{4}\s+FOMC Meetings</a>|\Z)',
            html, re.S):
        year = int(panel.group(1))
        body = panel.group(2)
        for row in re.finditer(
                r'fomc-meeting__month[^>]*>(?:<strong>)?\s*([A-Za-z]+)[^<]*'
                r'.*?fomc-meeting__date[^>]*>\s*([0-9]+)(?:\s*[-/]\s*([0-9]+))?',
                body, re.S):
            mon = months.get(row.group(1).strip().lower())
            if not mon:
                continue
            # A two-day meeting decides on its SECOND day; that is the date that
            # matters to amarket participant, so the later day is used.
            day = int(row.group(3) or row.group(2))
            # A range that wraps a month end (e.g. "29-1") ends in the next month.
            if row.group(3) and int(row.group(3)) < int(row.group(2)):
                mon, day = (mon % 12) + 1, int(row.group(3))
                if mon == 1:
                    year += 1
            try:
                iso = "%04d-%02d-%02d" % (year, mon, day)
                datetime.fromisoformat(iso)
            except ValueError:
                continue
            if iso not in scheduled:
                scheduled.append(iso)

    dates = sorted(set(past_dates) | set(scheduled))
    if not dates:
        return {"state": STATE_FAIL,
                "reason": "no meeting anchors or scheduled rows found; page layout changed",
                "contract": "SCRAPE_NO_STABLE_CONTRACT"}
    today = now.date().isoformat()
    upcoming = [d for d in dates if d >= today]
    past = [d for d in dates if d < today]
    if not upcoming:
        # Do NOT silently publish "no next meeting" -- the FOMC always has one.
        return {"state": "PARTIAL_SCHEDULE_NOT_PARSEABLE",
                "contract": "SCRAPE_NO_STABLE_CONTRACT",
                "source": "federalreserve.gov FOMC calendar",
                "meeting_dates_parsed_count": len(dates),
                "last_meeting_date": past[-1] if past else None,
                "next_meeting_date": None,
                "reason": ("past meetings parsed but no future meeting row was "
                           "readable; treat the forward calendar as UNAVAILABLE, "
                           "not as 'no meeting scheduled'")}
    return {
        "state": STATE_OK,
        "source": "federalreserve.gov FOMC calendar",
        "contract": "SCRAPE_NO_STABLE_CONTRACT",
        "meeting_dates_parsed_count": len(dates),
        "recent_and_upcoming_meetings": past[-2:] + upcoming[:4],
        "next_meeting_date": upcoming[0],
        "days_until_next_meeting": (
            datetime.fromisoformat(upcoming[0]).date() - now.date()).days,
        "last_meeting_date": past[-1] if past else None,
        "note": ("Decision dates. For a two-day meeting the second day is used, "
                 "because that is when the statement is released."),
    }


async def _statements(hub, limit: int = 5) -> Dict[str, Any]:
    try:
        xml = await _get_text(FOMC_RSS_URL)
    except Exception as exc:                                        # noqa: BLE001
        return {"state": STATE_FAIL, "error": type(exc).__name__}
    if not isinstance(xml, str) or "<item" not in xml:
        return {"state": STATE_FAIL, "reason": "monetary-policy RSS returned no items"}
    items: List[Dict[str, Any]] = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]:
        def _tag(name):
            m = re.search(r"<%s>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</%s>" % (name, name),
                          block, re.S)
            return (m.group(1).strip() if m else None)
        items.append({"title": _tag("title"), "published_at": _tag("pubDate"),
                      "link": _tag("link")})
    if not items:
        return {"state": STATE_FAIL, "reason": "RSS parsed but produced no entries"}
    return {"state": STATE_OK, "source": "federalreserve.gov monetary-policy RSS",
            "contract": "RSS_STRUCTURED_FEED", "items": items,
            "sentiment_scored": False,
            "note": ("Titles and publication timestamps only. No hawkish/dovish "
                     "score is produced: none has been validated on this project's "
                     "data, so publishing one beside a forecast would imply an "
                     "edge that has not been demonstrated.")}


async def build_fed_evidence(hub, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Collect Fed evidence. Never raises; never fabricates."""
    rate = await _policy_rate(hub)
    cal = await _fomc_calendar(hub, now=now)
    stm = await _statements(hub)
    ok = [b["state"] for b in (rate, cal, stm)].count(STATE_OK)
    return {
        "ok": ok > 0,
        "generated_at": _now(),
        "production_influence": False,
        "affects_published_probability": False,
        "scored": False,
        "classification": "PRODUCTION_EVIDENCE_ONLY",
        "sources_available": ok,
        "sources_total": 3,
        "policy_rate": rate,
        "fomc_calendar": cal,
        "statements": stm,
        "disclosure": ("Context only. No value on this payload enters the 4H/8H "
                       "probability, the confidence, or the Forward-OOS ledger."),
    }
