from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import fia_final_cockpit.api as api

base={'live':{'snapshot':{'status':'LIVE'},'forecast':{'status':'LIVE','direction':'BULLISH','bullish_probability':70,'bearish_probability':30}}}
for truth,expected in [
 ({'provider_overall':'ERROR','critical_missing':[],'stale_sources':[]},('UNAVAILABLE',False)),
 ({'provider_overall':'LIVE','critical_missing':['macro'],'stale_sources':[]},('DEGRADED',False)),
 ({'provider_overall':'LIVE','critical_missing':[],'stale_sources':['nq']},('DEGRADED',False)),
 ({'provider_overall':'LIVE','critical_missing':[],'stale_sources':[]},('LIVE',True)),
]:
    x=api._cockpit_truth_status(base,truth)
    assert (x['status'],x['truth_ready'])==expected,x
x=api._cockpit_truth_status({'live':{'snapshot':{'status':'UNKNOWN'},'forecast':{'status':'LIVE'}}},{'provider_overall':'LIVE','critical_missing':[],'stale_sources':[]})
assert x['status']=='DEGRADED' and not x['truth_ready'],x

# Installed model != successful inference. LIVE requires a fresh OK shadow.
orig_static,orig_health,orig_shadow=api._brain_static,api._ollama_health,api._latest_shadow
try:
    api._brain_static=lambda:{'installed':True,'root':'/tmp','model':'gpt-oss:20b','version':'6.6.1'}
    api._ollama_health=lambda:{'status':'LIVE','model_present':True,'models':['gpt-oss:20b']}
    api._latest_shadow=lambda root:{'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'FAIL_CLOSED','direction':'NO_EDGE'}
    x=api.brain_status(); assert x['status']=='READY_FAIL_CLOSED' and not x['fresh_successful_inference'],x
    api._latest_shadow=lambda root:{'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'OK','direction':'BULLISH'}
    x=api.brain_status(); assert x['status']=='LIVE' and x['fresh_successful_inference'],x
    api._latest_shadow=lambda root:{'generated_at_utc':(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat(),'status':'OK','direction':'BULLISH'}
    x=api.brain_status(); assert x['status']=='READY_STALE_INFERENCE' and not x['fresh_successful_inference'],x
finally:
    api._brain_static,api._ollama_health,api._latest_shadow=orig_static,orig_health,orig_shadow

# Frontend must fail closed too; no missing->50 visual fallback.
# V6.6.2: these assertions previously pinned IDENTIFIER NAMES ('localTruthReady',
# 'displayBullProbability') that the page no longer uses. The page was refactored and
# is in fact stricter than before, but the test failed on the rename rather than on
# behaviour. They now pin the SEMANTICS, which is what actually protects the user.
page=(ROOT.parent/'frontend/app/page.tsx').read_text(encoding='utf-8')

# 1) the cockpit truth flag must gate the display
assert 'finalCockpit.truth_ready === true' in page, 'truth_ready gate missing'

# 2) truth readiness must additionally require live forecast/snapshot/provider state
for token in ('forecastStatus === "LIVE"', 'snapshotStatus', 'providerOverall',
              'critical_missing', 'stale_sources'):
    assert token in page, 'truth-readiness composition missing: %s' % token

# 3) probabilities/confidence must fail closed to null, never to a neutral number
#    V6.6.7: the Obsidian cockpit renamed these bindings (bull8/bear8/bull4/bear4,
#    confidence8/confidence4) and gates each horizon separately. The names moved;
#    the protection did not. These assertions pin the BEHAVIOUR.
for token in ('const bull8 = truthReady ?', 'const bear8 = truthReady ?',
              'const bull4 = truthReady ?', 'const bear4 = truthReady ?',
              'const confidence8 = truthReady ?', 'const confidence4 = truthReady ?'):
    assert token in page, 'probability must be gated by truthReady: %s' % token
assert ': null;' in page, 'gated values must fall back to null'

# Every gated value must reach the PUBLISHED display through the gate.
# V6.6.8: raw/internal figures may still be shown, but ONLY inside the block that
# is explicitly labelled not-published. So the rule is positional, not absolute:
# nothing ungated may appear before that marker.
_MARKER = 'INTERNAL RESEARCH VALUE'
assert _MARKER in page, 'the internal research block must be explicitly labelled'
# Scan the published region only, and drop the gate DEFINITION lines
# ("const x = truthReady ? finite(...) : null") -- those implement the protection
# rather than bypass it.
_published_region = "\n".join(
    ln for ln in page.split(_MARKER)[0].splitlines()
    if "truthReady ?" not in ln)
for leak in ('pct(h8.confidence', 'pct(h4.confidence', 'pct(h4.bearish_probability',
             'finite(h4.bearish_probability)', 'finite(h8.confidence)',
             'h8.bullish_probability', 'h4.bullish_probability'):
    assert leak not in _published_region, (
        'ungated value rendered in the published region: %s' % leak)
# and the research block must say it is not tradeable
assert 'NOT PUBLISHED, NOT TRADE-READY' in page, 'research values must be labelled not-trade-ready'

# A withheld probability must not render as a directional distribution bar.
# .track paints its background with var(--bear); with a 0-width bull overlay that
# reads as a 100% bearish call for a figure the system refused to publish.
assert 'track${bull8 === null ? " withheld" : ""}' in page, '8H bar must go neutral when withheld'
assert 'mini${bull4 === null ? " withheld" : ""}' in page, '4H bar must go neutral when withheld'
assert 'PUBLISHED WITHHELD' in page, 'the withheld bar must say so on its face'

# 4) an explicit not-trustworthy presentation must exist (no silent neutral bias)
for token in ('"UNAVAILABLE"', 'NO EDGE', 'DO NOT TRUST BIAS'):
    assert token in page, 'explicit fail-closed presentation missing: %s' % token
assert 'truthBlockedReason' in page, 'the blocked reason must be shown, not just a dash'

# 5) the page must never coerce a missing probability into 0 or 50
assert 'bullish_probability || 0' not in page, 'missing probability coerced to 0'
assert 'bullish_probability ?? 50' not in page, 'missing probability coerced to 50'
assert 'Number(forecast.bullish_probability) || 0' not in page, 'Number(null)->0 coercion present'
for tok in ('bull8 === null ? "—"', 'bear8 === null ? "—"', 'bull4 === null ? "—"'):
    assert tok in page, 'a null probability must render as a dash: %s' % tok

print('PASS test_rc2_sol56_truth_status')
