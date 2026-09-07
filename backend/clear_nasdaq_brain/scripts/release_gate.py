#!/usr/bin/env python3
from pathlib import Path
import ast,subprocess,sys,json,py_compile
ROOT=Path(__file__).resolve().parents[1]; failures=[]; pyfiles=[p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts]
for p in pyfiles:
    try: ast.parse(p.read_text(encoding="utf-8"),filename=str(p),feature_version=(3,9))
    except Exception as e: failures.append("py39:%s:%s"%(p.relative_to(ROOT),e))
    try: py_compile.compile(str(p),doraise=True)
    except Exception as e: failures.append("compile:%s:%s"%(p.relative_to(ROOT),e))
for name,cmd in (("tests",[sys.executable,str(ROOT/"tests"/"run_all.py")]),("self_audit",[sys.executable,str(ROOT/"scripts"/"self_audit.py")])):
    r=subprocess.run(cmd,cwd=str(ROOT),capture_output=True,text=True,timeout=180)
    print("=== "+name+" ===\n"+r.stdout+r.stderr)
    if r.returncode: failures.append(name+" failed")
print(json.dumps({"ok":not failures,"python_files":len(pyfiles),"failures":failures},indent=2)); raise SystemExit(0 if not failures else 1)
