from __future__ import annotations
import json, math, statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""): return default
        return float(v)
    except Exception:
        return default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x); return 1.0/(1.0+z)
    z = math.exp(x); return z/(1.0+z)


def dt(v: Any) -> datetime:
    if isinstance(v, datetime): out=v
    else:
        s=str(v or "").strip().replace("Z", "+00:00")
        try: out=datetime.fromisoformat(s)
        except Exception: out=datetime.now(timezone.utc)
    if out.tzinfo is None: out=out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


def get(obj: Any, key: str, default: Any=None) -> Any:
    if isinstance(obj, dict): return obj.get(key, default)
    return getattr(obj, key, default)


def raw_snapshot(snapshot: Any) -> Dict[str, Any]:
    if isinstance(snapshot, dict) and isinstance(snapshot.get("data"), dict): return snapshot["data"]
    return snapshot if isinstance(snapshot, dict) else {}


def signal_map(forecast: Any) -> Dict[str, Dict[str, Any]]:
    out={}
    for s in list(get(forecast,"signals",[]) or []):
        name=str(get(s,"name","") or "").strip()
        if not name: continue
        fresh=str(get(s,"freshness","unknown") or "unknown")
        out[name]={"score": fnum(get(s,"score",0.0)), "weight": max(0.0,fnum(get(s,"weight",0.0))), "freshness":fresh}
    return out


def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs)!=len(ys) or len(xs)<4: return None
    mx=sum(xs)/len(xs); my=sum(ys)/len(ys)
    dx=[x-mx for x in xs]; dy=[y-my for y in ys]
    den=math.sqrt(sum(x*x for x in dx)*sum(y*y for y in dy))
    if den<=1e-12: return None
    return clamp(sum(a*b for a,b in zip(dx,dy))/den,-1.0,1.0)


def linear_slope(values: List[Tuple[datetime,float]]) -> float:
    if len(values)<2: return 0.0
    t0=values[0][0]
    xs=[(t-t0).total_seconds()/3600.0 for t,_ in values]; ys=[y for _,y in values]
    xb=sum(xs)/len(xs); yb=sum(ys)/len(ys)
    den=sum((x-xb)**2 for x in xs)
    return 0.0 if den<=1e-12 else sum((x-xb)*(y-yb) for x,y in zip(xs,ys))/den


def load_json(path: Path, default: Any=None) -> Any:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {} if default is None else default


def dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str), encoding="utf-8")


def missing(name: str, reason: str="source_not_connected") -> Dict[str, Any]:
    return {"name":name,"status":"MISSING_NOT_FAKED","value":None,"score":None,"reason":reason}
