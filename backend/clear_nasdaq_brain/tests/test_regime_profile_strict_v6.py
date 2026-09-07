from pathlib import Path
import tempfile,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.regime_memory import load
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'r.json'; p.write_text('{"enabled":true,"training_split":"TRAIN","n":30,"features":{"x":{"median":NaN,"mad":1}}}')
 bad=False
 try:load(str(p))
 except ValueError:bad=True
 assert bad
print('PASS test_regime_profile_strict_v6')
