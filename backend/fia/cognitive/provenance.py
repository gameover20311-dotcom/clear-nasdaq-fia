from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import EvidenceRecord
from .utils import as_float, parse_dt, stable_hash, utc_now_iso

ROOT = Path(__file__).resolve().parents[2]
LEDGER_DIR = ROOT / "fia_cognitive_data" / "ledger"
CHAIN_FILE = LEDGER_DIR / "ledger_chain.jsonl"

_SIGNAL_INSTRUMENT = {
    "NQ structure": "NQ/QQQ",
    "SPX confirmation": "SPX/SPY",
    "DXY": "DXY",
    "US10Y": "US10Y",
    "Mega-cap leadership": "NASDAQ-100 constituents",
    "Semiconductors": "NASDAQ semiconductors",
    "Breadth": "NASDAQ breadth",
    "News": "NASDAQ news",
    "Macro calendar": "US macro",
    "Earnings/guidance": "NASDAQ earnings",
}

_SOURCE_KEYS = {
    "DXY": ("dxy_source", "dxy_source_timestamp"),
    "US10Y": ("us10y_source", "us10y_source_timestamp"),
    "NQ structure": ("nq_structure_source", "nq_structure_timestamp"),
    "SPX confirmation": ("spx_source", "spx_source_timestamp"),
    "News": ("news_status", "news_timestamp"),
    "Macro calendar": ("macro_status", "macro_timestamp"),
    "Earnings/guidance": ("earnings_status", "earnings_timestamp"),
}


def _forecast_dict(forecast: Any) -> Dict[str, Any]:
    if hasattr(forecast, "model_dump"):
        return forecast.model_dump()
    if hasattr(forecast, "dict"):
        return forecast.dict()
    if isinstance(forecast, dict):
        return dict(forecast)
    return dict(getattr(forecast, "__dict__", {}) or {})


def _latency_seconds(observed_at: Optional[str], first_seen_at: Optional[str]) -> Optional[float]:
    a, b = parse_dt(observed_at), parse_dt(first_seen_at)
    if a is None or b is None:
        return None
    return max(0.0, (b - a).total_seconds())


def _signal_records(snapshot: Dict[str, Any], forecast: Any, first_seen_at: str) -> List[EvidenceRecord]:
    raw = snapshot.get("data", snapshot) if isinstance(snapshot, dict) else {}
    fc = _forecast_dict(forecast)
    result: List[EvidenceRecord] = []
    for signal in fc.get("signals", []) or []:
        if not isinstance(signal, dict):
            signal = getattr(signal, "__dict__", {}) or {}
        name = str(signal.get("name") or "UNKNOWN")
        freshness = str(signal.get("freshness") or "unknown")
        source_key, ts_key = _SOURCE_KEYS.get(name, (None, None))
        source = str(raw.get(source_key) or snapshot.get("provider") or "unknown") if source_key else str(snapshot.get("provider") or "derived")
        observed_at = raw.get(ts_key) if ts_key else None
        if observed_at is None:
            observed_at = snapshot.get("timestamp")
        status = "missing" if freshness.lower() in {"missing", "unavailable", "error"} else "available"
        payload = {
            "name": name,
            "score": signal.get("score"),
            "weight": signal.get("weight"),
            "freshness": freshness,
            "source": source,
            "observed_at": observed_at,
        }
        checksum = stable_hash(payload)
        result.append(EvidenceRecord(
            evidence_id=f"sig-{checksum[:16]}",
            category="signal",
            instrument=_SIGNAL_INSTRUMENT.get(name, "NASDAQ-100"),
            source=source,
            provider=str(snapshot.get("provider") or "derived"),
            observed_at=str(observed_at) if observed_at is not None else None,
            first_seen_at=first_seen_at,
            freshness=freshness,
            status=status,
            raw_value=signal.get("score"),
            normalized_value=as_float(signal.get("score")),
            quality=1.0 if status == "available" else 0.0,
            latency_seconds=_latency_seconds(str(observed_at) if observed_at is not None else None, first_seen_at),
            revision=str(raw.get("data_revision") or "unknown"),
            request_id=str(raw.get("request_id") or "") or None,
            checksum=checksum,
            metadata={
                "weight": signal.get("weight"),
                "detail": signal.get("detail"),
                "source_status": (fc.get("source_status") or {}).get(name),
            },
        ))
    return result


def _news_records(news_items: Iterable[Dict[str, Any]], first_seen_at: str) -> List[EvidenceRecord]:
    records: List[EvidenceRecord] = []
    for article in news_items or []:
        if not isinstance(article, dict):
            continue
        payload = {
            "headline": article.get("headline") or article.get("title"),
            "url": article.get("url"),
            "published_at": article.get("published_at") or article.get("publishedAt") or article.get("datetime"),
            "provider": article.get("provider"),
            "symbol": article.get("symbol"),
        }
        checksum = stable_hash(payload)
        published = payload["published_at"]
        records.append(EvidenceRecord(
            evidence_id=f"news-{checksum[:16]}",
            category="news",
            instrument=str(article.get("symbol") or "NASDAQ-100"),
            source=str(article.get("source") or "unknown"),
            provider=str(article.get("provider") or "unknown"),
            observed_at=str(published) if published is not None else None,
            first_seen_at=first_seen_at,
            freshness=str(article.get("freshness") or "unknown"),
            status="available",
            raw_value=article.get("headline") or article.get("title"),
            normalized_value=as_float((article.get("fia_news_trust") or {}).get("trust_score")),
            quality=as_float((article.get("fia_news_trust") or {}).get("trust_score"), 0.5) or 0.5,
            latency_seconds=_latency_seconds(str(published) if published is not None else None, first_seen_at),
            revision="original",
            url=str(article.get("url") or "") or None,
            checksum=checksum,
            metadata={
                "category": article.get("category"),
                "symbol": article.get("symbol"),
                "fia_context": article.get("fia_context") or {},
            },
        ))
    return records


def build_evidence_ledger(snapshot: Dict[str, Any], forecast: Any, news_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    first_seen_at = utc_now_iso()
    records = _signal_records(snapshot, forecast, first_seen_at)
    records.extend(_news_records(news_items or [], first_seen_at))
    fc = _forecast_dict(forecast)
    evidence_payload = [r.to_dict() for r in records]
    forecast_id = "fia-" + stable_hash({
        "generated_at": fc.get("generated_at"),
        "direction": fc.get("direction"),
        "bullish_probability": fc.get("bullish_probability"),
        "evidence": [r.checksum for r in records],
    })[:24]
    return {
        "forecast_id": forecast_id,
        "created_at": first_seen_at,
        "records": evidence_payload,
        "record_count": len(records),
        "available_count": sum(1 for r in records if r.status == "available"),
        "missing_count": sum(1 for r in records if r.status != "available"),
        "ledger_digest": stable_hash(evidence_payload),
    }


def persist_ledger(ledger: Dict[str, Any]) -> Dict[str, Any]:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    forecast_id = str(ledger.get("forecast_id") or "unknown")
    target = LEDGER_DIR / f"{forecast_id}.json"
    target.write_text(json.dumps(ledger, indent=2, default=str), encoding="utf-8")

    previous_hash = "GENESIS"
    if CHAIN_FILE.exists():
        try:
            last = CHAIN_FILE.read_text(encoding="utf-8").strip().splitlines()[-1]
            previous_hash = json.loads(last).get("record_hash") or "GENESIS"
        except Exception:
            previous_hash = "UNKNOWN"
    chain_record = {
        "forecast_id": forecast_id,
        "ledger_digest": ledger.get("ledger_digest"),
        "created_at": ledger.get("created_at"),
        "previous_hash": previous_hash,
    }
    chain_record["record_hash"] = stable_hash(chain_record)
    with CHAIN_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(chain_record, sort_keys=True) + "\n")
    return {"path": str(target), "chain_record": chain_record}


def verify_ledger_chain() -> Dict[str, Any]:
    if not CHAIN_FILE.exists():
        return {"ok": True, "records": 0, "status": "EMPTY"}
    previous = "GENESIS"
    count = 0
    for line_no, line in enumerate(CHAIN_FILE.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("previous_hash") != previous:
            return {"ok": False, "records": count, "broken_line": line_no, "reason": "previous_hash mismatch"}
        expected = stable_hash({k: v for k, v in row.items() if k != "record_hash"})
        if expected != row.get("record_hash"):
            return {"ok": False, "records": count, "broken_line": line_no, "reason": "record_hash mismatch"}
        previous = row.get("record_hash")
        count += 1
    return {"ok": True, "records": count, "status": "VERIFIED", "head_hash": previous}
