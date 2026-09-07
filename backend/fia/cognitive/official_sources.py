from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import httpx

from .utils import parse_dt

SEC_BASE = "https://data.sec.gov"


async def _sec_get(path: str) -> Optional[Dict[str, Any]]:
    ua = os.getenv("SEC_USER_AGENT", "CLEAR-NASDAQ-FIA research contact@example.com")
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}) as client:
            r = await client.get(SEC_BASE + path)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


async def sec_ticker_map() -> Dict[str, Dict[str, Any]]:
    data = await _sec_get("/files/company_tickers.json")
    result: Dict[str, Dict[str, Any]] = {}
    for row in (data or {}).values() if isinstance(data, dict) else []:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            result[ticker] = row
    return result


async def verify_sec_filing(symbol: str, as_of: Any, forms: Iterable[str] = ("8-K", "10-Q", "10-K"),
                            lookback_days: int = 10) -> Dict[str, Any]:
    dt = parse_dt(as_of) or datetime.now(timezone.utc)
    mapping = await sec_ticker_map()
    row = mapping.get(str(symbol).upper())
    if not row:
        return {"verified": False, "symbol": symbol, "reason": "ticker not found in SEC mapping"}
    cik = str(row.get("cik_str") or "").zfill(10)
    sub = await _sec_get(f"/submissions/CIK{cik}.json")
    recent = ((sub or {}).get("filings") or {}).get("recent") or {}
    accepted = recent.get("acceptanceDateTime") or []
    filing_dates = recent.get("filingDate") or []
    form_rows = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    primary_docs = recent.get("primaryDocument") or []
    allowed = {str(x) for x in forms}
    matches=[]
    for i, form in enumerate(form_rows):
        if form not in allowed: continue
        accepted_dt = parse_dt(accepted[i] if i < len(accepted) else None)
        if accepted_dt is None:
            fd = parse_dt((filing_dates[i] if i < len(filing_dates) else "") + "T23:59:59+00:00")
            accepted_dt = fd
        if accepted_dt is None or accepted_dt > dt or accepted_dt < dt - timedelta(days=lookback_days):
            continue
        accession = accessions[i] if i < len(accessions) else None
        doc = primary_docs[i] if i < len(primary_docs) else None
        accession_nodash = str(accession or "").replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{doc}" if accession and doc else None
        matches.append({"form":form,"accepted_at":accepted_dt.isoformat(),"filing_date":filing_dates[i] if i<len(filing_dates) else None,"accession":accession,"url":url})
    return {"verified": bool(matches), "symbol": symbol, "provider": "SEC EDGAR", "cik": cik,
            "matches": matches[:10], "policy": "Only filings accepted on or before as_of are eligible."}


async def verify_primary_event(symbols: Iterable[str], as_of: Any) -> Dict[str, Any]:
    results={}
    for symbol in sorted({str(s).upper() for s in symbols if s}):
        results[symbol]=await verify_sec_filing(symbol,as_of)
    return {"provider":"SEC EDGAR","as_of":str(as_of),"symbols":results,"verified_symbols":[s for s,v in results.items() if v.get("verified")]}
