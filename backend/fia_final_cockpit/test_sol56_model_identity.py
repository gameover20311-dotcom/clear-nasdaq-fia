from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_final_cockpit import api

class Resp:
    headers={}
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def read(self,n): return json.dumps({'models':[{'name':'gpt-oss:20b-malicious'}]}).encode()
old=api.urllib.request.urlopen
api.urllib.request.urlopen=lambda *a,**k: Resp()
try:
    x=api._ollama_health()
finally:
    api.urllib.request.urlopen=old
assert x.get('model_present') is False,x
print('PASS test_sol56_model_identity')
