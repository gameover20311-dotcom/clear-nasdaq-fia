from __future__ import annotations
import json
from pathlib import Path
from typing import Any,Dict
from fastapi import HTTPException
from .core import rolling_forward_metrics


def install_whole_system_backtest_routes(app, backend_root=None):
    root=Path(backend_root or Path(__file__).resolve().parents[1])
    result=root/'fia_whole_system_backtest/results/whole_system_backtest_report.json'

    @app.get('/api/backtest/whole-system/report')
    def whole_system_backtest_report():
        if not result.exists():
            return {'ok':True,'state':'NOT_RUN','final':False,'historical_1y_whole_system':None,'live_forward_oos':rolling_forward_metrics(root)}
        try:
            obj=json.loads(result.read_text(encoding='utf-8'))
        except Exception as e:
            raise HTTPException(status_code=500,detail='whole-system report unreadable') from e
        # Refresh forward OOS at read time without modifying historical results.
        obj['live_forward_oos']=rolling_forward_metrics(root)
        return {'ok':True,**obj}

    @app.get('/api/backtest/whole-system/status')
    def whole_system_backtest_status():
        if not result.exists():return {'ok':True,'state':'NOT_RUN','final':False}
        try:
            obj=json.loads(result.read_text(encoding='utf-8'))
            return {'ok':True,'state':obj.get('state'),'final':bool(obj.get('final')),'progress':obj.get('progress'),'report_sha256':obj.get('report_sha256')}
        except Exception as e:
            raise HTTPException(status_code=500,detail='whole-system status unreadable') from e
