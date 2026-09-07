import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import yfinance as yf

from fia.providers import ProviderHub
from fia_backtest_phase15.historical_news import filter_news_point_in_time, normalize_timestamp

SYMBOLS = ["NVDA","MSFT","AAPL","AMZN","META","AVGO","GOOGL","GOOG","TSLA","NFLX","AMD","MU","INTC","QCOM","SMCI"]
MEGA = {"NVDA":.14,"MSFT":.10,"AAPL":.09,"AMZN":.08,"META":.07,"AVGO":.06,"GOOGL":.06,"GOOG":.04,"TSLA":.04,"NFLX":.03}
SEMIS = ["NVDA","AVGO","AMD","MU","INTC","QCOM","SMCI"]
TICKERS = {"nq":"NQ=F","qqq":"QQQ","spy":"SPY","dxy":"DX-Y.NYB","us10y":"^TNX", **{s:s for s in SYMBOLS}}


def utc_ts(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clamp(x):
    return max(-1.0, min(1.0, float(x)))


def norm_change(pct):
    return None if pct is None else clamp(float(pct) / 2.0)


@lru_cache(maxsize=64)
def hist1h(ticker):
    return yf.Ticker(ticker).history(period="2y", interval="1h", auto_adjust=False, prepost=False)


@lru_cache(maxsize=2)
def nq5m():
    return yf.Ticker("NQ=F").history(period="60d", interval="5m", auto_adjust=False, prepost=True)


def asof(df, target, interval_minutes=0):
    """Return only bars that were fully completed by target.

    Yahoo timestamps intraday bars by bar start.  A 17:00 1h bar
    contains information from 17:00-18:00, so it is not point-in-time
    safe at 17:00.  We therefore require bar_start + interval <= target.
    """
    if df is None or df.empty:
        return df
    t = target.replace(tzinfo=None) if df.index.tz is None else target.astimezone(df.index.tz)
    if interval_minutes:
        from datetime import timedelta as _td
        cutoff = t - _td(minutes=interval_minutes)
    else:
        cutoff = t
    return df[df.index <= cutoff]


def quote_asof(ticker, target):
    df = asof(hist1h(ticker), target, 60)
    if df is None or df.empty:
        return {"price":None,"prev_close":None,"dp":None}
    c = df["Close"].dropna()
    if c.empty:
        return {"price":None,"prev_close":None,"dp":None}
    price = float(c.iloc[-1])
    day = c.index[-1].date()
    prev = c[[x.date() < day for x in c.index]]
    if prev.empty:
        return {"price":price,"prev_close":None,"dp":None}
    pc = float(prev.iloc[-1])
    dp = ((price-pc)/pc)*100.0 if pc else None
    return {"price":price,"prev_close":pc,"dp":dp}


def market_asof(target):
    q = {k:quote_asof(t, target) for k,t in TICKERS.items()}
    mega_total = mega_weight = 0.0
    mega_details = {}
    for s,w in MEGA.items():
        sig = norm_change(q[s]["dp"])
        if sig is None: continue
        mega_total += sig*w; mega_weight += w
        mega_details[s] = {"change_percent":q[s]["dp"],"signal":round(sig,4),"weight":w}
    semi = [norm_change(q[s]["dp"]) for s in SEMIS]
    semi = [x for x in semi if x is not None]
    breadth = [norm_change(q[s]["dp"]) for s in SYMBOLS]
    breadth = [x for x in breadth if x is not None]
    dxy = norm_change(q["dxy"]["dp"])
    dxy = -dxy if dxy is not None else None
    y = q["us10y"]["price"]
    us10y = None if y is None else (0.35 if y < 4.0 else (0.0 if y < 4.5 else -0.5))
    return {
        "symbol":"QQQ",
        "price":q["qqq"]["price"],
        "nq_futures_price":q["nq"]["price"],
        "nq_structure":norm_change(q["qqq"]["dp"]),
        "spx_confirmation":norm_change(q["spy"]["dp"]),
        "dxy":dxy,"us10y":us10y,"us10y_value":y,
        "mega_cap":clamp(mega_total/mega_weight) if mega_weight else None,
        "semis":sum(semi)/len(semi) if semi else None,
        "breadth":sum(breadth)/len(breadth) if breadth else None,
        "mega_cap_details":mega_details,
        "semi_members_available":len(semi),"breadth_members_available":len(breadth),
        "provider_quotes_available":sum(v["price"] is not None for v in q.values()),
        "provider_quotes_requested":len(q),
        "provider_candle_evidence":"available" if q["qqq"]["price"] is not None else "missing",
    }


def liquidity_asof(target, hub):
    """Point-in-time historical version of the project's advanced NQ liquidity logic.

    Uses completed NQ bars only and the same UTC session windows used by
    ProviderHub.get_nq_liquidity_intelligence()/session_window_for_date().
    """
    try:
        df = asof(nq5m(), target, 5)
        resolution = "5m"
    except Exception:
        df = None

    if df is None or df.empty:
        df = asof(hist1h("NQ=F"), target, 60)
        resolution = "1h_fallback"

    if df is None or df.empty:
        return {"nq_liquidity_evidence":"missing","liquidity_signal":None}

    # Normalize to UTC because the advanced live intelligence uses UTC windows.
    if df.index.tz is None:
        df = df.tz_localize(timezone.utc)
    else:
        df = df.tz_convert(timezone.utc)

    now = target.astimezone(timezone.utc)
    levels = {}

    for back in range(8):
        d = now.date() - timedelta(days=back)
        for session in ("ASIA", "LONDON", "NEW_YORK"):
            start, end = hub.session_window_for_date(session, d)
            if start is None or end is None:
                continue
            rows = df[(df.index >= start) & (df.index < end)]
            if rows.empty:
                continue
            hk = session.lower() + "_high"
            lk = session.lower() + "_low"
            if hk not in levels:
                levels[hk] = float(rows["High"].max())
            if lk not in levels:
                levels[lk] = float(rows["Low"].min())

        required = {"asia_high","asia_low","london_high","london_low","new_york_high","new_york_low"}
        if required.issubset(levels):
            break

    closes = df["Close"].dropna()
    if closes.empty:
        return {"nq_liquidity_evidence":"missing","liquidity_signal":None}

    price = float(closes.iloc[-1])
    recent = df.tail(12)
    result = {
        "nq_liquidity_evidence": "available",
        "liquidity_resolution": resolution,
        "nq_price": price,
        **levels,
    }

    targets = []
    for name, level in levels.items():
        distance = float(level) - price
        distance_abs = abs(distance)
        result[f"{name}_distance"] = distance
        result[f"{name}_distance_abs"] = distance_abs
        targets.append({"level":name,"price":float(level),"distance":distance,"distance_abs":distance_abs})
    targets.sort(key=lambda x: x["distance_abs"])
    result["nearest_liquidity"] = targets[0]["level"] if targets else None
    result["nearest_liquidity_distance"] = targets[0]["distance"] if targets else None

    bull = bear = False
    for session in ("asia", "london", "new_york"):
        high = levels.get(f"{session}_high")
        low = levels.get(f"{session}_low")
        if high is None or low is None:
            continue
        swept_high = bool((recent["High"] > high).any())
        swept_low = bool((recent["Low"] < low).any())
        reclaimed_high = swept_high and price < high
        reclaimed_low = swept_low and price > low
        result[f"{session}_high_sweep"] = swept_high
        result[f"{session}_low_sweep"] = swept_low
        result[f"{session}_high_reclaim"] = reclaimed_high
        result[f"{session}_low_reclaim"] = reclaimed_low
        bear = bear or reclaimed_high
        bull = bull or reclaimed_low

    if bull and not bear:
        direction, signal, conflict = "BULLISH", 1.0, "LOW"
    elif bear and not bull:
        direction, signal, conflict = "BEARISH", -1.0, "LOW"
    elif bull and bear:
        direction, signal, conflict = "NEUTRAL", 0.0, "HIGH"
    else:
        direction, signal, conflict = "NEUTRAL", 0.0, "NONE"

    result.update(liquidity_direction=direction, liquidity_signal=signal, liquidity_conflict=conflict)

    ranked=[]
    for item in targets:
        ranked.append({
            "level": item["level"],
            "price": item["price"],
            "direction": "UP" if item["level"].endswith("_high") else "DOWN",
            "distance": item["distance"],
            "rank_score": round(1.0/(1.0+item["distance_abs"]),6),
        })
    result["liquidity_targets"] = ranked[:6]

    positive_volumes = [float(v) for v in recent.get("Volume", []) if float(v) > 0]
    if positive_volumes and "Volume" in df.columns:
        avg = sum(positive_volumes)/len(positive_volumes)
        current = float(df["Volume"].iloc[-1])
        result["nq_relative_volume"] = current/avg if avg else None
    else:
        result["nq_relative_volume"] = None

    return result


def normalize_article(a, provider, category, symbol=None):
    title = str(a.get("headline") or a.get("title") or "").strip()
    if not title: return None
    src = a.get("source")
    src = (src.get("name") or src.get("id")) if isinstance(src,dict) else (src or a.get("author") or "Unknown")
    desc = str(a.get("summary") or a.get("description") or "").strip()
    return {"headline":title,"description":desc,"summary":desc,"source":src,"url":a.get("url") or "","published_at":a.get("datetime") or a.get("publishedAt") or a.get("published_at"),"provider":provider,"category":category,"symbol":symbol,"raw":a}


def recency_asof(article, target):
    try: published = normalize_timestamp(article.get("published_at"))
    except Exception: return .50
    h = max(0.0,(target-published).total_seconds()/3600)
    for limit,score in [(1,1),(3,.95),(6,.9),(12,.82),(24,.72),(48,.55),(72,.4),(120,.25)]:
        if h <= limit: return score
    return .15



def normalize_polygon_article(a):
    if not isinstance(a, dict):
        return None
    title = str(a.get("title") or "").strip()
    if not title:
        return None
    publisher = a.get("publisher") or {}
    source = publisher.get("name") if isinstance(publisher, dict) else str(publisher or "Unknown")
    desc = str(a.get("description") or "").strip()
    return {
        "headline": title,
        "description": desc,
        "summary": desc,
        "source": source or "Unknown",
        "url": a.get("article_url") or "",
        "published_at": a.get("published_utc"),
        "provider": "Polygon",
        "category": "market",
        "symbol": None,
        "tickers": a.get("tickers") or [],
        "raw": a,
    }


async def polygon_news_window(target, hub):
    key = hub.keys.get("POLYGON_API_KEY")
    if not key:
        return [], "missing_key", 0

    start = target - timedelta(days=3)
    url = "https://api.polygon.io/v2/reference/news"
    params = {
        "published_utc.gte": start.isoformat(),
        "published_utc.lte": target.isoformat(),
        "order": "asc",
        "sort": "published_utc",
        "limit": 1000,
        "apiKey": key,
    }

    rows = []
    pages = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while url and pages < 25:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            except Exception:
                break

            batch = payload.get("results") or []
            if isinstance(batch, list):
                rows.extend(batch)

            pages += 1
            next_url = payload.get("next_url")
            if not next_url:
                break

            url = next_url
            params = {"apiKey": key}

    articles = []
    for row in rows:
        item = normalize_polygon_article(row)
        if item:
            articles.append(item)
    return articles, "available" if articles else "missing", pages


async def news_asof(target, hub):
    start=(target-timedelta(days=3)).date().isoformat()
    end=target.date().isoformat()
    articles=[]

    polygon_articles, polygon_status, polygon_pages = await polygon_news_window(target, hub)
    articles.extend(polygon_articles)

    # Finnhub company news stays as a supplemental second source.
    if hub.keys.get("FINNHUB_API_KEY"):
        tasks=[
            hub.get(
                "https://finnhub.io/api/v1/company-news",
                {"symbol":s,"from":start,"to":end,"token":hub.keys["FINNHUB_API_KEY"]},
                timeout=20,
            )
            for s in SYMBOLS
        ]
        for s,r in zip(SYMBOLS, await asyncio.gather(*tasks,return_exceptions=True)):
            if isinstance(r,Exception):
                continue
            for a in r if isinstance(r,list) else []:
                x=normalize_article(a,"Finnhub","company",s)
                if x:
                    articles.append(x)

    articles=filter_news_point_in_time(articles,target.isoformat())

    lower = target - timedelta(days=3)
    filtered=[]
    for a in articles:
        try:
            published = normalize_timestamp(a.get("published_at"))
        except Exception:
            continue
        if published >= lower:
            filtered.append(a)
    articles=filtered

    if not articles:
        return {
            "news":None,
            "historical_news_evidence":"missing",
            "historical_news_articles":0,
            "historical_news_clusters":0,
            "historical_news_kept":0,
            "historical_news_directional":0,
            "historical_news_polygon_articles":0,
            "historical_news_polygon_pages":polygon_pages,
            "historical_news_polygon_status":polygon_status,
        }

    enriched=[]
    for a in articles:
        x=dict(a)
        try:
            x["fia_context"]=hub.analyze_news_context_v3_calibrated(x)
            x["fia_nasdaq_relevance"]=hub.analyze_nasdaq_relevance_v3(x,x["fia_context"])
        except Exception:
            x["fia_context"]={}
            x["fia_nasdaq_relevance"]={}
        enriched.append(x)

    reps=hub.detect_duplicate_news(enriched).get("representatives",enriched)
    quality=hub.filter_news_quality(reps)

    old=hub.calculate_news_recency_score
    hub.calculate_news_recency_score=lambda a:recency_asof(a,target)
    try:
        trusted=hub.apply_news_trust_scores(quality)
    finally:
        hub.calculate_news_recency_score=old

    num=den=0.0
    kept=directional=0
    for a in trusted:
        trust=a.get("fia_news_trust",{}) or {}
        if str(trust.get("decision","")).upper()=="REJECT":
            continue
        kept+=1
        ctx=hub.analyze_news_context(a)
        d=str(ctx.get("direction","neutral")).lower()
        if d not in ("bullish","bearish"):
            continue
        directional+=1
        sign=1 if d=="bullish" else -1
        dc=float(ctx.get("direction_confidence",0) or 0)
        ts=float(trust.get("trust_score",0) or 0)
        rel=float((a.get("fia_nasdaq_relevance",{}) or {}).get("nasdaq_relevance_score",0) or 0)
        cc=float((a.get("fia_context",{}) or {}).get("primary_event_confidence",0) or 0)
        w=max(.05,ts*max(.1,rel)*max(.25,cc))
        num += sign*dc*w
        den += w

    polygon_count=sum(1 for a in articles if a.get("provider")=="Polygon")
    finnhub_count=sum(1 for a in articles if a.get("provider")=="Finnhub")

    return {
        "news":clamp(num/den) if den else 0.0,
        "historical_news_evidence":"available",
        "historical_news_articles":len(articles),
        "historical_news_clusters":len(reps),
        "historical_news_kept":kept,
        "historical_news_directional":directional,
        "historical_news_polygon_articles":polygon_count,
        "historical_news_finnhub_articles":finnhub_count,
        "historical_news_polygon_pages":polygon_pages,
        "historical_news_polygon_status":polygon_status,
    }


async def earnings_asof(target, hub):
    key=hub.keys.get("FINNHUB_API_KEY")
    if not key: return {"earnings":None,"historical_earnings_evidence":"missing"}
    payload=await hub.get("https://finnhub.io/api/v1/calendar/earnings",{"from":(target.date()-timedelta(days=1)).isoformat(),"to":(target.date()+timedelta(days=7)).isoformat(),"token":key},timeout=20)
    events=[e for e in (payload or {}).get("earningsCalendar",[]) if e.get("symbol") in set(SYMBOLS)]
    ny=target.astimezone(hub.NY_TZ); pos=neg=count=0
    for e in events:
        try: d=datetime.fromisoformat(str(e.get("date"))).date()
        except Exception: continue
        done=d < ny.date()
        if d==ny.date():
            hour=str(e.get("hour") or "").lower(); done=(hour=="bmo" and ny.hour>=10) or (hour=="amc" and ny.hour>=18)
        if not done: continue
        try: actual=float(e["epsActual"]); estimate=float(e["epsEstimate"])
        except (TypeError,ValueError,KeyError): continue
        if actual>estimate: pos+=1; count+=1
        elif actual<estimate: neg+=1; count+=1
    score=clamp((pos-neg)/count) if count else (0.0 if events else None)
    return {"earnings":score,"historical_earnings_evidence":"available" if events else "missing","earnings_events":len(events),"earnings_surprises_counted":count,"earnings_positive":pos,"earnings_negative":neg}


async def build_full_historical_snapshot(timestamp):
    target=utc_ts(timestamp); hub=ProviderHub()
    market=await asyncio.to_thread(market_asof,target)
    liquidity=await asyncio.to_thread(liquidity_asof,target,hub)
    news,earnings=await asyncio.gather(news_asof(target,hub),earnings_asof(target,hub))
    data={**market,**liquidity,**news,**earnings}
    data["macro"]=0.0
    data["historical_macro_evidence"]="live_parity_neutral"
    return {"status":"HISTORICAL_FULL","timestamp":target.isoformat(),"data":data}


async def main():
    import sys
    ts=sys.argv[1] if len(sys.argv)>1 else "2026-08-31T17:00:00+00:00"
    s=await build_full_historical_snapshot(ts); d=s["data"]
    print("=== FIA PHASE 19 FULL SNAPSHOT ===")
    for k in ["nq_futures_price","price","nq_structure","spx_confirmation","dxy","us10y","mega_cap","semis","breadth","liquidity_direction","liquidity_signal","liquidity_conflict","news","historical_news_articles","historical_news_polygon_articles","historical_news_finnhub_articles","historical_news_kept","historical_news_directional","earnings","earnings_events","macro"]: print(k,"=",d.get(k))
    print("market members =",d.get("provider_quotes_available"),"/",d.get("provider_quotes_requested"))
    print("liquidity evidence =",d.get("nq_liquidity_evidence"),d.get("liquidity_resolution"))
    print("news evidence =",d.get("historical_news_evidence"))
    print("earnings evidence =",d.get("historical_earnings_evidence"))
    print("macro evidence =",d.get("historical_macro_evidence"))
    print("=== PHASE 19 SNAPSHOT COMPLETE ===")

if __name__=="__main__": asyncio.run(main())
