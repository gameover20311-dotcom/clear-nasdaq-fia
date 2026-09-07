import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fia.liquidity import build_liquidity_map, build_liquidity_groups

TRACKED={"NVDA","MSFT","AAPL","AMZN","META","AVGO","GOOGL","GOOG","TSLA","NFLX","AMD","MU","INTC","QCOM","SMCI"}
CANDIDATES=[
    (
        Path('fia_backtest_phase29/results/phase29_outcome_revalidated_1y.csv'),
        'PHASE 29 OUTCOME-REVALIDATED',
        Path('fia_backtest_phase29/results/phase29_outcome_revalidated_1y_summary.json'),
    ),
    (Path('fia_backtest_phase21/results/phase21_no_neutral_backtest_1y.csv'),'PHASE 21 NO-NEUTRAL',None),
    (Path('fia_backtest_phase20/results/phase20_full_backtest_1y.csv'),'PHASE 20',None),
]

def truthy(v): return str(v or '').strip().lower() in {'1','true','yes','y'}
def num(v):
    try: return float(v)
    except: return None

def ser(v):
    if is_dataclass(v): return asdict(v)
    if hasattr(v,'model_dump'): return v.model_dump()
    if hasattr(v,'dict'): return v.dict()
    if hasattr(v,'__dict__'): return v.__dict__
    return v

def accuracy(rows,h):
    ak=f'actual_{h}'; ck=f'correct_{h}'
    r=[x for x in rows if str(x.get(ak) or '').strip()]
    c=sum(1 for x in r if truthy(x.get(ck)))
    return {'resolved':len(r),'correct':c,'accuracy':round(100*c/len(r),2) if r else None}

def conf(rows,h):
    ak=f'actual_{h}'; out=[]
    for lo,hi in [(0,50),(50,60),(60,70),(70,101)]:
        s=[x for x in rows if str(x.get(ak) or '').strip() and num(x.get('confidence')) is not None and lo<=num(x.get('confidence'))<hi]
        c=sum(1 for x in s if str(x.get('predicted') or '').upper()==str(x.get(ak) or '').upper())
        out.append({'band':f'{lo}-{hi}%','n':len(s),'accuracy':round(100*c/len(s),2) if s else None})
    return out

def brier(rows,h):
    ak=f'actual_{h}'; vals=[]
    for x in rows:
        a=str(x.get(ak) or '').upper(); p=num(x.get('bullish_probability'))
        if a not in {'BULLISH','BEARISH'} or p is None: continue
        y=1.0 if a=='BULLISH' else 0.0
        vals.append((p/100-y)**2)
    return {'n':len(vals),'brier':round(sum(vals)/len(vals),4) if vals else None}

def monthly(rows):
    g=defaultdict(list)
    for x in rows:
        ts=str(x.get('timestamp') or '')
        if len(ts)>=7: g[ts[:7]].append(x)
    out=[]
    for m in sorted(g):
        a4=accuracy(g[m],'4h'); a8=accuracy(g[m],'8h')
        out.append({'month':m,'forecasts':len(g[m]),'accuracy_4h':a4['accuracy'],'resolved_4h':a4['resolved'],'accuracy_8h':a8['accuracy'],'resolved_8h':a8['resolved']})
    return out

def earnings_compare(rows):
    e=[x for x in rows if truthy(x.get('earnings_catalyst_risk'))]
    o=[x for x in rows if not truthy(x.get('earnings_catalyst_risk'))]
    return {'earnings_catalyst_days':{'days':len(e),'4h':accuracy(e,'4h'),'8h':accuracy(e,'8h')},'other_days':{'days':len(o),'4h':accuracy(o,'4h'),'8h':accuracy(o,'8h')}}

def load_backtest():
    selected=next((x for x in CANDIDATES if x[0].exists()),None)
    if not selected: return {'available':False,'reason':'Backtest CSV not found'}
    p,phase,summary_path=selected
    with p.open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
    summary={}
    if summary_path and summary_path.exists():
        try: summary=json.loads(summary_path.read_text(encoding='utf-8'))
        except Exception: summary={}
    return {
        'available':True,'phase':phase,'file':str(p),'forecasts':len(rows),
        'authenticity':{
            'status':summary.get('status') or 'LEGACY_RESULT',
            'official_market_grade_claim_eligible':bool(summary.get('official_market_grade_claim_eligible',False)),
            'outcome_source':summary.get('outcome_source') or 'legacy',
            'prediction_digest_preserved':summary.get('prediction_digest_preserved'),
            'note':summary.get('reason_official_claim_is_withheld') or 'Historical research result; not a future guarantee.',
        },
        'accuracy_4h':accuracy(rows,'4h'),'accuracy_8h':accuracy(rows,'8h'),
        'predictions':dict(Counter(str(x.get('predicted') or 'UNKNOWN').upper() for x in rows)),
        'confidence_4h':conf(rows,'4h'),'confidence_8h':conf(rows,'8h'),
        'brier_4h':brier(rows,'4h'),'brier_8h':brier(rows,'8h'),
        'monthly':monthly(rows),'earnings_comparison':earnings_compare(rows),
        'data_quality':{
            'future_eps_used':sum(1 for x in rows if truthy(x.get('earnings_future_eps_used'))),
            'liquidity_resolutions':dict(Counter(str(x.get('liquidity_resolution') or 'missing') for x in rows)),
            'liquidity_contracts':dict(Counter(str(x.get('liquidity_contract') or 'missing') for x in rows)),
            'news_evidence':dict(Counter(str(x.get('news_evidence') or 'missing') for x in rows)),
            'earnings_evidence':dict(Counter(str(x.get('earnings_evidence') or 'missing') for x in rows)),
        },
    }

async def upcoming(hub):
    key=getattr(hub,'keys',{}).get('FINNHUB_API_KEY')
    if not key: return {'available':False,'events':[]}
    start=datetime.now(timezone.utc).date(); end=start+timedelta(days=7)
    r=await hub.get('https://finnhub.io/api/v1/calendar/earnings',{'from':start.isoformat(),'to':end.isoformat(),'token':key},timeout=15)
    events=[]
    for e in (r or {}).get('earningsCalendar',[]):
        s=str(e.get('symbol') or '').upper()
        if s in TRACKED:
            events.append({'symbol':s,'date':e.get('date'),'hour':e.get('hour'),'eps_estimate':e.get('epsEstimate'),'revenue_estimate':e.get('revenueEstimate')})
    events.sort(key=lambda e:(str(e.get('date') or ''),str(e.get('hour') or ''),e['symbol']))
    return {'available':True,'events':events}

async def build_dashboard_payload(hub, build_forecast):
    snapshot = await hub.snapshot()
    if isinstance(snapshot, dict) and isinstance(snapshot.get('data'), dict):
        data = snapshot['data']
        forecast_input = snapshot
    elif isinstance(snapshot, dict):
        data = snapshot
        forecast_input = {'data': data}
    else:
        data = {}
        forecast_input = {'data': {}}
    forecast = build_forecast(forecast_input)
    levels = build_liquidity_map(data)
    groups = build_liquidity_groups(data)
    try:
        from fia.cognitive import build_cognitive_report
        cognitive = build_cognitive_report(forecast_input, forecast, horizon='8h', persist=False)
    except Exception as exc:
        cognitive = {'ok': False, 'status': 'UNAVAILABLE', 'error': str(exc)}

    # V6.6.2 PRE-MOVE WATCH: separate 4H/8H pre-move distributions, explicit
    # WATCH/SHIFT_DETECTED/NO_EDGE/DEGRADED/STALE/MISSING_DATA state, gated
    # probability-shift detection and a stable evidence-derived forecast id.
    try:
        from fia.premove_watch import build_watch
        # provider health is already enriched onto the snapshot by the provider layer
        provider_health_payload = {
            'provider_health': (data.get('provider_health') or {}),
            'source_health': (data.get('source_health') or {}),
        }
        premove_watch = build_watch(forecast, snapshot, provider_health_payload, persist=True)
    except Exception as exc:
        premove_watch = {'ok': False, 'state': 'UNAVAILABLE',
                         'error': type(exc).__name__ + ': ' + str(exc)}

    # V6.6.2: publish the underlying market observation time alongside the
    # response-build time. The Brain freshness gate ages the DATA, not the envelope.
    _data_as_of = None
    try:
        _ts = snapshot.get('timestamp') if isinstance(snapshot, dict) else None
        if _ts is not None:
            _data_as_of = datetime.fromtimestamp(float(_ts), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        _data_as_of = None

    # ---------------------------------------------------------------- V6.6.3
    # CROSS-LAYER CONSISTENCY. Three estimators run on the same snapshot:
    #   base engine (live.forecast)      - single 8H distribution
    #   pre-move    (live.premove_watch) - separate 4H and 8H, horizon-weighted
    #   cognitive   (live.cognitive)     - 8H only, specialist fusion + analogy
    # They can legitimately disagree because they are different models, but that
    # disagreement must never be silent. The canonical trader-facing 4H/8H
    # probability is the PRE-MOVE layer; the others are published alongside it
    # with the divergence measured explicitly.
    def _dirof(v):
        return str((v or {}).get('direction') or '').upper() or None
    def _bullof(v):
        return num((v or {}).get('bullish_probability'))
    _pm8 = ((premove_watch.get('horizons') or {}).get('8h') or {}) if isinstance(premove_watch, dict) else {}
    _fc = ser(forecast) if not isinstance(forecast, dict) else forecast
    _cog = cognitive if isinstance(cognitive, dict) else {}
    _dirs = {'base_engine': _dirof(_fc), 'premove_8h': _dirof(_pm8), 'cognitive_8h': _dirof(_cog)}
    _known = [d for d in _dirs.values() if d in ('BULLISH', 'BEARISH')]
    _bulls = {k: v for k, v in (('base_engine', _bullof(_fc)),
                                ('premove_8h', _bullof(_pm8)),
                                ('cognitive_8h', _bullof(_cog))) if v is not None}
    # Separate genuine directional calls from abstentions before comparing them.
    _ABSTAIN = {'NO_EDGE', 'NEUTRAL', 'UNKNOWN', ''}
    _directional = [v for v in _dirs.values() if str(v or '').upper() not in _ABSTAIN]
    _directional_names = [k for k, v in _dirs.items()
                          if str(v or '').upper() not in _ABSTAIN]
    _abstaining = [k for k, v in _dirs.items() if str(v or '').upper() in _ABSTAIN]
    _canon_abstains = str(_dirs.get('premove_8h') or '').upper() in _ABSTAIN

    forecast_consistency = {
        'canonical_source': 'live.premove_watch.horizons',
        'canonical_reason': ('the pre-move layer is the only one that publishes 4H and 8H '
                             'separately with horizon-specific evidence weights'),
        'directions': _dirs,
        'bullish_probabilities': _bulls,
        # V6.6.7: an ABSTENTION IS NOT AGREEMENT. `_known` filters out unknown
        # values, which meant a canonical NO_EDGE alongside two BULLISH estimators
        # reported directions_agree=true -- implying a consensus that the
        # published forecast explicitly declined to make.
        'directions_agree': ((len(set(_directional)) <= 1) if _directional else None),
        'directional_estimators': sorted(_directional_names),
        'abstaining_estimators': sorted(_abstaining),
        'canonical_is_abstaining': _canon_abstains,
        'agreement_scope': ('directional estimators only; abstentions are excluded '
                            'from the comparison and never counted as agreement'),
        'max_bullish_spread_points': (round(max(_bulls.values()) - min(_bulls.values()), 3)
                                      if len(_bulls) > 1 else None),
        'note': ('Different estimators may disagree. Each publishes its direction from its OWN '
                 'raw evidence score; calibration is slope-only and cannot decide a sign. '
                 'Disagreement is reported, never averaged away.'),
    }

    # V6.6.7 FED EVIDENCE (context only, never a forecast input).
    # Built in an isolated module that neither engine nor premove_watch imports,
    # and attached to the payload AFTER the forecast and the pre-move view have
    # already been computed, so it cannot influence either even by accident.
    try:
        from fia.fed_evidence import build_fed_evidence
        fed_evidence = await build_fed_evidence(hub)
    except Exception as exc:
        fed_evidence = {'ok': False, 'classification': 'PRODUCTION_EVIDENCE_ONLY',
                        'production_influence': False,
                        'affects_published_probability': False,
                        'state': 'SOURCE_FAILURE',
                        'error': type(exc).__name__ + ': ' + str(exc)}

    # ------------------------------------------------------------- V6.6.7
    # PRODUCTION / RESEARCH BOUNDARY. Every component is classified so no part
    # of the system has ambiguous influence on the published forecast. This is
    # provenance only -- it computes nothing and changes no probability.
    #
    # Three-Brain and the cognitive reasoning layer are RESEARCH_ONLY on evidence,
    # not by assertion: driving the cognitive layer from maximally bullish to
    # maximally bearish -- including critic.hard_hold=True -- leaves the published
    # 4H/8H probability and confidence byte-identical. premove_watch imports
    # nothing from the reasoning path except the calibration model file.
    component_map = {
        'PRODUCTION_FORECAST': {
            'BASE_FIA_engine': 'fia/engine.py build_forecast -> weighted evidence score',
            'premove_watch': 'fia/premove_watch.py -> the published 4H and 8H distributions',
            'premove_calibration': 'slope-only, intercept pinned at 0; cannot decide a sign',
            'conviction_gate': 'NO_EDGE when |published-50| < 2.0 or confidence < 5.0',
            'session_freshness_gate': 'venue-aware admissibility of every input',
        },
        'PRODUCTION_EVIDENCE_ONLY': {
            'provider_health': 'source availability/freshness; gates but does not score',
            'liquidity_levels': 'execution context; not a directional input',
            'news': 'scored, summary-only, primary_source_ratio 0.0',
            'forward_oos_ledger': 'immutable record; never feeds a forecast',
            'fed_evidence': ('FRED policy rate + FOMC calendar + monetary-policy RSS; '
                             'timestamped, unscored, isolated module'),
        },
        'SHADOW_CANDIDATE': {},
        'RESEARCH_ONLY': {
            'three_brain_v74': 'zero production influence (proven by extremes test); FAIL_CLOSED on last run',
            'cognitive_layer': 'hypotheses/critic/analogy/fusion -- reasoning context only',
            'chart_analyst': 'user-initiated; external paid vision API; never feeds the forecast',
            'phase33': 'validated on 78 untouched holdout rows and LOST to BASE_FIA; not adopted',
            'phase34': 'never validated; 1 of 13 sources; replay blocked',
        },
        'REJECTED': {
            'phase33_live_probability': 'calibration_approved_for_live_probability = false',
        },
        'LEGACY_ARCHIVE': {
            'historical_backtests': 'phase29 supplies retrospective metrics; phase20/21 fallback only',
        },
        'NOT_AVAILABLE': {
            'macro_event_calendar': ('data.macro is None; no event-calendar producer. '
                                     'source_health.macro reports NO_PRODUCER_IMPLEMENTED'),
            'fed_scored_signal': ('no validated hawkish/dovish score exists for this '
                                  'project, so none is produced; the Fed EVIDENCE '
                                  'producer is context only'),
            'earnings_surprise': 'no released-surprise evidence',
            'consensus_expectations': 'not available free; SURPRISE_UNAVAILABLE',
        },
        'three_brain_affects_published_probability': False,
        'cognitive_affects_published_probability': False,
        'note': ('Only PRODUCTION_FORECAST components influence the published 4H/8H '
                 'probability. Everything else is context, record or research.'),
    }

    return {'ok':True,'generated_at':datetime.now(timezone.utc).isoformat(),'data_as_of':_data_as_of,'live':{'snapshot':snapshot,'forecast':ser(forecast),'cognitive':cognitive,'premove_watch':premove_watch,'data_as_of':_data_as_of,'liquidity':{k:ser(v) for k,v in levels.items()},'liquidity_groups':{g:{'instrument':v.get('instrument'),'current_price':v.get('current_price'),'levels':{k:ser(x) for k,x in (v.get('levels') or {}).items()}} for g,v in groups.items()},'upcoming_earnings':await upcoming(hub)},'backtest':load_backtest(),'forecast_consistency':forecast_consistency,'component_map':component_map,'fed_evidence':fed_evidence}
