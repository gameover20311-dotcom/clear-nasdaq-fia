#!/usr/bin/env python3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess,sys,os
ROOT=Path(__file__).resolve().parents[1]
tests=sorted((ROOT/'tests').glob('test_*.py'))

def run_one(p):
    try:
        r=subprocess.run([sys.executable,str(p)],cwd=str(ROOT),capture_output=True,text=True,timeout=20)
        return p.name,r.returncode,r.stdout,r.stderr
    except subprocess.TimeoutExpired as e:
        return p.name,124,(e.stdout or ''),(e.stderr or '')+'\nTIMEOUT>20s\n'

# Tests are subprocess-isolated and use temporary paths for mutable fixtures.
# Parallel execution makes repeated release gates practical without weakening assertions.
results={}
workers=min(6,max(1,len(tests)))
with ThreadPoolExecutor(max_workers=workers) as ex:
    futs={ex.submit(run_one,p):p for p in tests}
    for f in as_completed(futs):
        name,rc,out,err=f.result();results[name]=(rc,out,err)

fails=[]
for p in tests:
    rc,out,err=results[p.name]
    if out: print(out,end='')
    if err: print(err,end='',file=sys.stderr)
    if rc: fails.append((p.name,'rc='+str(rc)))
print(f"\n{len(tests)-len(fails)}/{len(tests)} tests PASS")
if fails:
    print('FAIL:',fails);raise SystemExit(1)
