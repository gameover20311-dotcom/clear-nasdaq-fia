#!/usr/bin/env python3
from pathlib import Path
import argparse,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.cases import read_jsonl,valid_output_hash
from fia_brain.failure_memory import record
ap=argparse.ArgumentParser(); ap.add_argument('case_id'); ap.add_argument('actual_direction',choices=['BULLISH','BEARISH']); a=ap.parse_args()
cases={str(x['case_id']):x for x in read_jsonl(ROOT/'benchmarks/cases.jsonl')}; outs={str(x['case_id']):x for x in read_jsonl(ROOT/'benchmarks/local_outputs.jsonl')}
if a.case_id not in cases or a.case_id not in outs: raise SystemExit('case/output missing')
if not valid_output_hash(outs[a.case_id]): raise SystemExit('output hash invalid; refusing autopsy')
row=record(str(ROOT/'data/memory/failure_memory.jsonl'),cases[a.case_id],outs[a.case_id],a.actual_direction,datetime.now(timezone.utc).isoformat())
print(row['verdict'])
