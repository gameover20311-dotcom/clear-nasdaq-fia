from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.local_llm import _extract_json, LocalModelError

assert _extract_json('{"x":1}') == {"x":1}
assert _extract_json('```json\n{"x":2}\n```') == {"x":2}
assert _extract_json('preface that is not JSON {"x":{"y":"} inside string"}} trailing prose') == {"x":{"y":"} inside string"}}

failed=False
try:
    _extract_json('draft {"x":1} revised {"x":2}')
except LocalModelError as e:
    failed="multiple distinct" in str(e)
assert failed

failed=False
try:
    _extract_json('{"x":NaN}')
except LocalModelError:
    failed=True
assert failed
print("PASS test_balanced_json_extractor_v6_5")
