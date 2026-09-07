from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

from .utils import as_float, clamp, mean, parse_dt, stable_hash

TRACKED_WEIGHTS = {
    "NVDA": 0.14, "MSFT": 0.10, "AAPL": 0.09, "AMZN": 0.08,
    "META": 0.07, "AVGO": 0.06, "GOOGL": 0.06, "GOOG": 0.04,
    "TSLA": 0.04, "NFLX": 0.03, "AMD": 0.03, "MU": 0.02,
    "INTC": 0.015, "QCOM": 0.015, "SMCI": 0.01,
}

COMPANY_NAMES = {
    "NVIDIA": "NVDA", "MICROSOFT": "MSFT", "APPLE": "AAPL",
    "AMAZON": "AMZN", "META": "META", "FACEBOOK": "META",
    "BROADCOM": "AVGO", "ALPHABET": "GOOGL", "GOOGLE": "GOOGL",
    "TESLA": "TSLA", "NETFLIX": "NFLX", "AMD": "AMD",
    "MICRON": "MU", "INTEL": "INTC", "QUALCOMM": "QCOM",
    "SUPER MICRO": "SMCI",
}

PRIMARY_DOMAINS = {
    "sec.gov", "www.sec.gov", "federalreserve.gov", "www.federalreserve.gov",
    "bls.gov", "www.bls.gov", "bea.gov", "www.bea.gov", "treasury.gov",
    "www.treasury.gov", "whitehouse.gov", "www.whitehouse.gov",
}

HIGH_QUALITY_DOMAINS = {
    "reuters.com", "www.reuters.com", "bloomberg.com", "www.bloomberg.com",
    "wsj.com", "www.wsj.com", "ft.com", "www.ft.com", "cnbc.com", "www.cnbc.com",
    "apnews.com", "www.apnews.com", "marketwatch.com", "www.marketwatch.com",
}

POSITIVE = {"beat", "beats", "upgrade", "raises", "raised", "record", "surge", "growth", "strong", "approval", "win", "rebound", "cut rates", "rate cut"}
NEGATIVE = {"miss", "misses", "downgrade", "cuts", "cut guidance", "weak", "decline", "probe", "ban", "lawsuit", "tariff", "sanction", "recession", "rate hike", "selloff"}

EVENT_PATTERNS = [
    ("earnings", {"earnings", "eps", "revenue", "guidance", "quarter", "forecast"}),
    ("fed", {"federal reserve", "fed", "fomc", "powell", "rate cut", "rate hike"}),
    ("inflation", {"cpi", "pce", "inflation", "prices"}),
    ("labor", {"payroll", "payrolls", "jobs", "unemployment", "nfp"}),
    ("growth", {"gdp", "growth", "recession", "ism"}),
    ("regulation", {"regulation", "antitrust", "probe", "lawsuit", "ban"}),
    ("geopolitics", {"war", "sanctions", "tariff", "geopolitical", "china", "taiwan"}),
    ("technology", {"ai", "chip", "semiconductor", "product", "launch", "datacenter"}),
]

STOP = {"the","a","an","and","or","of","to","in","for","on","with","from","at","by","as","is","are","was","were","after","before","says","said","will","could","would","amid"}


def _text(article: Dict[str, Any]) -> str:
    return " ".join([
        str(article.get("headline") or article.get("title") or ""),
        str(article.get("description") or article.get("summary") or ""),
    ]).strip()


def _domain(url: Any) -> str:
    try:
        return urlparse(str(url or "")).netloc.lower()
    except Exception:
        return ""


def _tokens(text: str) -> Set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in STOP}


def _similarity(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _sentiment(text: str) -> float:
    low = text.lower()
    pos = sum(1 for w in POSITIVE if w in low)
    neg = sum(1 for w in NEGATIVE if w in low)
    if pos + neg == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / (pos + neg)))


def _entities(article: Dict[str, Any], text: str) -> List[str]:
    found: Set[str] = set()
    raw_symbol = str(article.get("symbol") or "").upper().strip()
    if raw_symbol in TRACKED_WEIGHTS:
        found.add(raw_symbol)
    upper = text.upper()
    for sym in TRACKED_WEIGHTS:
        if re.search(rf"\b{re.escape(sym)}\b", upper):
            found.add(sym)
    for name, sym in COMPANY_NAMES.items():
        if name in upper:
            found.add(sym)
    return sorted(found)


def _event_type(text: str) -> str:
    low = text.lower()
    scores = []
    for name, words in EVENT_PATTERNS:
        hits = sum(1 for word in words if word in low)
        if hits:
            scores.append((hits, name))
    return max(scores)[1] if scores else "general_market"


def _source_quality(article: Dict[str, Any]) -> Tuple[float, str]:
    domain = _domain(article.get("url"))
    source = str(article.get("source") or "").lower()
    if domain in PRIMARY_DOMAINS:
        return 1.0, "PRIMARY_OFFICIAL"
    if domain in HIGH_QUALITY_DOMAINS or any(x in source for x in ("reuters", "bloomberg", "wall street journal", "financial times", "cnbc", "associated press")):
        return 0.9, "HIGH_QUALITY_MEDIA"
    trust = as_float((article.get("fia_news_trust") or {}).get("trust_score"))
    if trust is not None:
        return clamp(trust), "PROVIDER_TRUST_SCORE"
    return 0.5, "UNVERIFIED_SECONDARY"


def _recency(published: Any, as_of: datetime) -> float:
    dt = parse_dt(published)
    if dt is None:
        return 0.35
    age = max(0.0, (as_of - dt).total_seconds() / 3600.0)
    return math.exp(-age / 36.0)


def _surprise(article: Dict[str, Any]) -> Optional[float]:
    raw = article.get("raw") if isinstance(article.get("raw"), dict) else article
    actual = as_float(raw.get("actual") or raw.get("epsActual") or raw.get("reported"))
    estimate = as_float(raw.get("estimate") or raw.get("epsEstimate") or raw.get("consensus"))
    if actual is None or estimate is None:
        return None
    denom = max(abs(estimate), 1e-9)
    return max(-2.0, min(2.0, (actual - estimate) / denom))


def analyze_news(articles: Iterable[Dict[str, Any]], as_of: Optional[datetime] = None) -> Dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    normalized: List[Dict[str, Any]] = []
    for article in articles or []:
        if not isinstance(article, dict):
            continue
        text = _text(article)
        if not text:
            continue
        published = article.get("published_at") or article.get("publishedAt") or article.get("datetime")
        pdt = parse_dt(published)
        if pdt is not None and pdt > as_of:
            continue
        quality, source_class = _source_quality(article)
        entities = _entities(article, text)
        event = _event_type(text)
        sentiment = as_float((article.get("fia_context") or {}).get("directional_score"))
        if sentiment is None:
            raw_direction = str((article.get("fia_context") or {}).get("direction") or "").upper()
            if raw_direction == "BULLISH": sentiment = 0.55
            elif raw_direction == "BEARISH": sentiment = -0.55
            else: sentiment = _sentiment(text)
        relevance = min(1.0, 0.20 + sum(TRACKED_WEIGHTS.get(s, 0.0) for s in entities) * 2.5)
        if event in {"fed", "inflation", "labor", "growth"}:
            relevance = max(relevance, 0.8)
        elif event in {"geopolitics", "regulation"}:
            relevance = max(relevance, 0.6)
        normalized.append({
            "article_id": "news-" + stable_hash({"text": text, "url": article.get("url"), "published": published})[:16],
            "headline": article.get("headline") or article.get("title"),
            "description": article.get("description") or article.get("summary"),
            "url": article.get("url"),
            "domain": _domain(article.get("url")),
            "source": article.get("source"),
            "provider": article.get("provider"),
            "published_at": str(published) if published is not None else None,
            "source_quality": round(quality, 3),
            "source_class": source_class,
            "is_primary_source": source_class == "PRIMARY_OFFICIAL",
            "entities": entities,
            "event_type": event,
            "sentiment": round(float(sentiment or 0.0), 3),
            "relevance": round(relevance, 3),
            "recency": round(_recency(published, as_of), 3),
            "surprise": _surprise(article),
            "tokens": _tokens(text),
            "market_reaction_pct": as_float(article.get("market_reaction_pct")),
        })

    clusters: List[List[int]] = []
    assigned: Set[int] = set()
    for i, item in enumerate(normalized):
        if i in assigned:
            continue
        cluster = [i]
        assigned.add(i)
        for j in range(i + 1, len(normalized)):
            if j in assigned:
                continue
            if _similarity(item["tokens"], normalized[j]["tokens"]) >= 0.68:
                cluster.append(j); assigned.add(j)
        clusters.append(cluster)

    cluster_meta: Dict[int, Dict[str, Any]] = {}
    for cidx, members in enumerate(clusters):
        sources = {normalized[i]["domain"] or str(normalized[i]["source"] or normalized[i]["provider"] or "unknown") for i in members}
        primary = any(normalized[i]["is_primary_source"] for i in members)
        cluster_id = f"cluster-{cidx+1:03d}"
        for i in members:
            cluster_meta[i] = {"cluster_id": cluster_id, "cluster_size": len(members), "independent_sources": len(sources), "primary_confirmed": primary}

    weighted_scores = []
    contradictions = []
    processed = []
    for i, item in enumerate(normalized):
        meta = cluster_meta[i]
        novelty = 1.0 / math.sqrt(max(1, meta["cluster_size"]))
        confirmation = min(1.0, meta["independent_sources"] / 3.0)
        primary_bonus = 1.0 if meta["primary_confirmed"] else 0.85
        priced_in = None
        reaction = item["market_reaction_pct"]
        if reaction is not None:
            aligned = (reaction > 0 and item["sentiment"] > 0) or (reaction < 0 and item["sentiment"] < 0)
            priced_in = bool(aligned and abs(reaction) >= 0.5)
        surprise = item["surprise"]
        surprise_factor = 1.0 if surprise is None else min(1.25, 0.9 + abs(surprise) * 0.25)
        impact = item["source_quality"] * item["relevance"] * item["recency"] * novelty * primary_bonus * surprise_factor
        if priced_in is True:
            impact *= 0.65
        score = item["sentiment"] * impact
        weighted_scores.append(score)
        out = {k: v for k, v in item.items() if k != "tokens"}
        out.update(meta)
        out.update({"novelty": round(novelty, 3), "confirmation": round(confirmation, 3), "priced_in": priced_in, "impact": round(impact, 3), "directional_contribution": round(score, 4)})
        processed.append(out)

    by_cluster = defaultdict(list)
    for item in processed:
        by_cluster[item["cluster_id"]].append(item)
    for cluster_id, members in by_cluster.items():
        signs = {1 if m["sentiment"] > 0.15 else -1 if m["sentiment"] < -0.15 else 0 for m in members}
        if 1 in signs and -1 in signs:
            contradictions.append({"cluster_id": cluster_id, "reason": "materially opposite sentiment across similar stories", "articles": [m["article_id"] for m in members]})

    primary_ratio = sum(1 for x in processed if x["is_primary_source"]) / len(processed) if processed else 0.0
    directional = sum(weighted_scores)
    norm = sum(abs(x) for x in weighted_scores)
    score = directional / norm if norm > 1e-9 else 0.0
    return {
        "available": bool(processed),
        "articles": processed,
        "article_count": len(processed),
        "duplicate_clusters": len(clusters),
        "primary_source_ratio": round(primary_ratio, 3),
        "directional_score": round(max(-1.0, min(1.0, score)), 4),
        "contradictions": contradictions,
        "top_impact": sorted(processed, key=lambda x: abs(x["directional_contribution"]), reverse=True)[:10],
        "policy": {
            "future_articles_rejected": True,
            "duplicate_detection": "headline-token Jaccard clustering",
            "primary_verification": "official-domain allowlist; otherwise unverified secondary",
            "priced_in_analysis": "only asserted when an explicit post-event market reaction is supplied",
            "unknown_is_not_neutral": True,
        },
    }
