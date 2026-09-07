from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from fia_brain.evidence_intelligence import cluster_correlated,evidence_cluster_map
from fia_brain.ensemble import aggregate
recs=[]
for i,leaf in enumerate(['price','change_pct','direction','high','low','open','close','volume'],1): recs.append({'evidence_id':f'E{i:04d}','source':'/api/dashboard','path':f'live.market.QQQ.{leaf}','value':i})
clusters=cluster_correlated(recs)
assert len(clusters)==1,clusters
cm=evidence_cluster_map(recs); ids={r['evidence_id'] for r in recs}|{'E9999'}
bull={'direction':'BULLISH','bullish_probability':80,'bearish_probability':20,'confidence':80,'evidence_ids':[r['evidence_id'] for r in recs],'counter_evidence_ids':[],'unknowns':[]}
bear={'direction':'BEARISH','bullish_probability':20,'bearish_probability':80,'confidence':80,'evidence_ids':['E9999'],'counter_evidence_ids':[],'unknowns':[]}
cm['E9999']='C999'
r=aggregate([bull,bear],ids,cm)
assert r['bullish_probability']==50.0,r
print('PASS test_correlation_ensemble_v661')
