from __future__ import annotations
import fcntl, json, os, tempfile
from pathlib import Path
from typing import Any, Dict, List, Union, Optional
from .util import sha256_obj, utc_now
from .evidence import validate_ledger_integrity
from .evidence_genome import build as build_genome

def _loads(line: str) -> Dict[str,Any]:
    def bad(x): raise ValueError("non-finite JSON forbidden")
    x=json.loads(line,parse_constant=bad)
    if not isinstance(x,dict): raise ValueError("row not object")
    return x

def read_jsonl(path: Union[str,Path]) -> List[Dict[str,Any]]:
    p=Path(path)
    if not p.exists(): return []
    out=[]
    with p.open("r",encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            if line.strip():
                try: out.append(_loads(line))
                except Exception as e: raise ValueError("invalid row %d: %s"%(n,e))
    return out

def _atomic_write_rows(p: Path,rows: List[Dict[str,Any]]) -> None:
    p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=p.name+".",suffix=".tmp",dir=str(p.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n")
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
        dfd=os.open(str(p.parent),os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def upsert_by_case(path: Union[str,Path],row: Dict[str,Any],allow_replace: bool=False) -> None:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); lockp=p.with_suffix(p.suffix+".lock")
    cid=str(row.get("case_id") or "")
    if not cid: raise ValueError("row missing case_id")
    with lockp.open("a+") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        try:
            rows=read_jsonl(p); idx={str(x.get("case_id")):i for i,x in enumerate(rows)}
            if cid in idx and not allow_replace: raise ValueError("duplicate/immutable case_id: "+cid)
            if cid in idx: rows[idx[cid]]=row
            else: rows.append(row)
            rows.sort(key=lambda x:str(x.get("case_id","")))
            _atomic_write_rows(p,rows)
        finally:
            fcntl.flock(lock.fileno(),fcntl.LOCK_UN)

def append_unique(path: Union[str,Path],row: Dict[str,Any]) -> None:
    upsert_by_case(path,row,allow_replace=False)

def make_case(case_id: str,split: str,snapshot: Dict[str,Any],ledger: Dict[str,Any],
              source_quality: Optional[Dict[str,Any]]=None, evidence_genome: Optional[Dict[str,Any]]=None) -> Dict[str,Any]:
    sp=str(split).upper()
    if sp not in {"TRAIN","DEV","HOLDOUT"}: raise ValueError("split must be TRAIN/DEV/HOLDOUT")
    ok,errors=validate_ledger_integrity(ledger)
    if not ok: raise ValueError("invalid evidence ledger: "+";".join(errors))
    computed_genome=build_genome(ledger)
    if evidence_genome and str(evidence_genome.get('evidence_genome_sha256'))!=str(computed_genome.get('evidence_genome_sha256')):
        raise ValueError('evidence genome does not match ledger')
    case={"case_id":case_id,"split":sp,"captured_at_utc":utc_now(),
          "snapshot_sha256":snapshot.get("snapshot_sha256"),"ledger_sha256":ledger.get("ledger_sha256"),
          "atomic_evidence_endpoint":snapshot.get("atomic_evidence_endpoint"),
          "source_quality":source_quality or {},
          "evidence_genome":computed_genome,
          "ledger":ledger}
    case["case_sha256"]=sha256_obj(case)
    return case

def output_hash(row: Dict[str,Any]) -> str:
    return sha256_obj({k:v for k,v in row.items() if k!="output_sha256"})

def bind_output(case: Dict[str,Any],output: Dict[str,Any],model_label: Optional[str]=None) -> Dict[str,Any]:
    row={"case_id":case["case_id"],"case_sha256":case["case_sha256"],"ledger_sha256":case["ledger_sha256"],
         "split":case.get("split"),"final":output.get("final",output),
         "status":output.get("status"),"model":model_label or output.get("model")}
    if output.get('reasoning_signature') is not None: row['reasoning_signature']=output.get('reasoning_signature')
    row["output_sha256"]=output_hash(row)
    return row

def valid_output_hash(row: Dict[str,Any]) -> bool:
    try: return str(row.get("output_sha256"))==output_hash(row)
    except Exception: return False
