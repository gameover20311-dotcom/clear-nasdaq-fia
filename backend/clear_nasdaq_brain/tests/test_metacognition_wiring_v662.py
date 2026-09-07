from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/'fia_brain'/'final_three_brain.py').read_text(encoding='utf-8')
tree=ast.parse(src)
calls=[]
for n in ast.walk(tree):
    if isinstance(n,ast.Call) and isinstance(n.func,ast.Name): calls.append(n.func.id)
assert 'assess_metacognition' in calls,calls
assert '"metacognition":meta' in src
assert 'float(meta["confidence_cap"])' in src
print('PASS test_metacognition_wiring_v662')
