from __future__ import annotations
from typing import Any
from .phase35_data_foundation import DATA_DIR
import json

def install_phase35_routes(app:Any):
    paths={getattr(r,'path',None) for r in getattr(app,'routes',[])}
    if '/api/phase35/status' not in paths:
        @app.get('/api/phase35/status')
        async def phase35_status():
            p=DATA_DIR/'backfill_manifest.json';e=DATA_DIR/'enrichment_summary.json'
            return {'ok':True,'phase':'PHASE35','data_backfill':json.loads(p.read_text()) if p.exists() else {'status':'NOT_RUN'},'enrichment':json.loads(e.read_text()) if e.exists() else {'status':'NOT_RUN'},'broker_execution':False}
