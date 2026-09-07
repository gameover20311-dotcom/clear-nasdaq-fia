from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fia_brain.market_twin import build,confidence_cap
g={'chains':[{'driver':'US10Y','polarity':'BULLISH_NQ','strength':80,'evidence_ids':['E1']},{'driver':'US10Y','polarity':'BEARISH_NQ','strength':70,'evidence_ids':['E2']}]}
t=build(g); assert t['driver_count']==1 and t['max_contradiction']>0.8 and confidence_cap(t)<=45
h=t['market_twin_sha256']; g['chains'][0]['strength']=10; assert build(g)['market_twin_sha256']!=h
print('PASS test_market_twin_v6')
