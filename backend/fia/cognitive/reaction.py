from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from .utils import as_float, parse_dt


def _normalize_candles(candles: Dict[str,Any]) -> List[Dict[str,Any]]:
    if not candles or candles.get("s") not in {None,"ok"}:
        return []
    ts=candles.get("t") or []; closes=candles.get("c") or []
    rows=[]
    for t,c in zip(ts,closes):
        try:
            dt=parse_dt(float(t))
            val=float(c)
        except Exception:
            continue
        if dt is not None: rows.append({"timestamp":dt,"close":val})
    rows.sort(key=lambda x:x["timestamp"])
    return rows


def annotate_market_reaction(articles: Iterable[Dict[str,Any]], candles: Dict[str,Any],
                             minutes_after: int = 30) -> List[Dict[str,Any]]:
    rows=_normalize_candles(candles)
    times=[r["timestamp"] for r in rows]
    out=[]
    for article in articles or []:
        item=dict(article)
        published=parse_dt(article.get("published_at") or article.get("publishedAt") or article.get("datetime"))
        if published is None or not rows:
            item["market_reaction_pct"]=None; item["reaction_status"]="UNAVAILABLE"; out.append(item); continue
        i=bisect_left(times,published)
        j=bisect_left(times,published+timedelta(minutes=minutes_after))
        if i>=len(rows) or j>=len(rows):
            item["market_reaction_pct"]=None; item["reaction_status"]="UNRESOLVED"; out.append(item); continue
        p0=rows[i]["close"]; p1=rows[j]["close"]
        item["market_reaction_pct"]=round((p1/p0-1)*100,4) if p0 else None
        item["reaction_status"]="OBSERVED_QQQ_AFTER_PUBLICATION"
        item["reaction_window_minutes"]=minutes_after
        out.append(item)
    return out
