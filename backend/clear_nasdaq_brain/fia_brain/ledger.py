from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Union
from .util import sha256_obj, utc_now

GENESIS="0"*64

def _loads(line: str) -> Dict[str, Any]:
    def bad(x): raise ValueError("non-finite JSON forbidden")
    obj=json.loads(line,parse_constant=bad)
    if not isinstance(obj,dict): raise ValueError("ledger row must be object")
    return obj

def _read(path: Path) -> List[Dict[str, Any]]:
    if not path.exists(): return []
    out=[]
    with path.open("r",encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            if line.strip():
                try: out.append(_loads(line))
                except Exception as e: raise ValueError("invalid ledger row %d: %s"%(n,e))
    return out

def _verify_rows(rows: List[Dict[str,Any]]) -> Dict[str,Any]:
    prev=GENESIS
    seen=set()
    for i,row in enumerate(rows):
        rh=row.get("record_hash")
        if not isinstance(rh,str) or len(rh)!=64 or rh in seen:
            return {"ok":False,"rows":len(rows),"bad_index":i,"reason":"invalid/duplicate record_hash"}
        if row.get("prev_hash")!=prev:
            return {"ok":False,"rows":len(rows),"bad_index":i,"reason":"prev_hash mismatch"}
        body={k:v for k,v in row.items() if k!="record_hash"}
        if rh!=sha256_obj(body):
            return {"ok":False,"rows":len(rows),"bad_index":i,"reason":"record_hash mismatch"}
        seen.add(rh); prev=rh
    return {"ok":True,"rows":len(rows),"head_hash":prev}

def _anchor_path(p: Path) -> Path:
    return p.with_suffix(p.suffix+".head.json")

def _write_anchor(p: Path, state: Dict[str,Any]) -> None:
    a=_anchor_path(p); a.parent.mkdir(parents=True,exist_ok=True)
    payload={"rows":int(state.get("rows",0)),"head_hash":str(state.get("head_hash",GENESIS))}
    payload["anchor_sha256"]=sha256_obj(payload)
    tmp=a.with_suffix(a.suffix+".tmp")
    tmp.write_text(json.dumps(payload,sort_keys=True,separators=(",",":")),encoding="utf-8")
    os.replace(tmp,a)

def initialize_head_anchor(path: Union[str,Path]) -> Dict[str,Any]:
    p=Path(path); state=_verify_rows(_read(p))
    if not state.get("ok"): raise RuntimeError("cannot anchor invalid ledger")
    _write_anchor(p,state); return state

def verify(path: Union[str,Path], require_anchor: bool=False) -> Dict[str,Any]:
    p=Path(path)
    try:
        state=_verify_rows(_read(p))
        if not state.get("ok"): return state
        a=_anchor_path(p)
        if not a.exists():
            if require_anchor and state.get("rows",0)>0:
                return {"ok":False,"rows":state.get("rows",0),"reason":"ledger head anchor missing"}
            return state
        anchor=_loads(a.read_text(encoding="utf-8"))
        ah=anchor.get("anchor_sha256"); body={k:v for k,v in anchor.items() if k!="anchor_sha256"}
        if ah!=sha256_obj(body): return {"ok":False,"rows":state.get("rows",0),"reason":"ledger head anchor checksum mismatch"}
        if int(anchor.get("rows",-1))!=int(state.get("rows",0)) or str(anchor.get("head_hash"))!=str(state.get("head_hash")):
            return {"ok":False,"rows":state.get("rows",0),"reason":"ledger head anchor mismatch"}
        return state
    except Exception as e: return {"ok":False,"rows":0,"reason":type(e).__name__+": "+str(e)}
def _pre_append_state(p: Path) -> Dict[str,Any]:
    rows=_read(p)
    state=_verify_rows(rows)
    if not state.get("ok"):
        raise RuntimeError("ledger integrity failure: "+str(state))
    anchor=_anchor_path(p)
    if anchor.exists():
        anchored=verify(p,require_anchor=True)
        if not anchored.get("ok"):
            raise RuntimeError("ledger integrity failure: "+str(anchored))
    elif state.get("rows",0)>0:
        # A non-empty unanchored ledger is ambiguous: it may be a legitimate
        # legacy chain or a tampered chain whose external head anchor was deleted.
        # Never auto-trust/re-anchor it during append. Legacy migration must call
        # initialize_head_anchor() explicitly before normal operation.
        raise RuntimeError("ledger head anchor missing; explicit migration required")
    return state


def append(path: Union[str,Path],payload: Dict[str,Any]) -> Dict[str,Any]:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    lockp=p.with_suffix(p.suffix+".lock")
    with lockp.open("a+") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        try:
            state=_pre_append_state(p)
            row={"created_at_utc":utc_now(),"prev_hash":state["head_hash"],"payload":payload}
            row["record_hash"]=sha256_obj(row)
            line=json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n"
            fd=os.open(str(p),os.O_APPEND|os.O_CREAT|os.O_WRONLY,0o600)
            try:
                os.write(fd,line.encode("utf-8")); os.fsync(fd)
            finally: os.close(fd)
            dfd=os.open(str(p.parent),os.O_RDONLY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
            post=_verify_rows(_read(p))
            if not post["ok"] or post["head_hash"]!=row["record_hash"]:
                raise RuntimeError("ledger verification failed after append")
            _write_anchor(p,post)
            return row
        finally:
            fcntl.flock(lock.fileno(),fcntl.LOCK_UN)


def append_unique_payload(path: Union[str,Path],payload: Dict[str,Any],key: str="case_id") -> Dict[str,Any]:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    lockp=p.with_suffix(p.suffix+".lock")
    with lockp.open("a+") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        try:
            state=_pre_append_state(p); rows=_read(p)
            wanted=str(payload.get(key) or "")
            if not wanted: raise ValueError("payload missing unique key: "+key)
            for existing in rows:
                ep=(existing.get("payload") or {})
                if str(ep.get(key) or "")==wanted:
                    raise ValueError("duplicate immutable payload key %s=%s"%(key,wanted))
            row={"created_at_utc":utc_now(),"prev_hash":state["head_hash"],"payload":payload}
            row["record_hash"]=sha256_obj(row)
            line=json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n"
            fd=os.open(str(p),os.O_APPEND|os.O_CREAT|os.O_WRONLY,0o600)
            try: os.write(fd,line.encode("utf-8")); os.fsync(fd)
            finally: os.close(fd)
            dfd=os.open(str(p.parent),os.O_RDONLY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
            post=_verify_rows(_read(p))
            if not post["ok"] or post["head_hash"]!=row["record_hash"]:
                raise RuntimeError("ledger verification failed after append")
            _write_anchor(p,post)
            return row
        finally:
            fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
