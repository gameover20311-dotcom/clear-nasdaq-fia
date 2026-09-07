"""V6.6.2 regression: concept-level future-outcome alias boundary.

BEFORE (V6.6.1): _future_semantic_path matched a narrow token list. An independent
audit fed it 21 outcome aliases and 18 slipped through (settled_direction,
verified_move, post_move_pct, eod_close, close_after_8h, px_t_plus_4h, y_true,
hit_target, excursion, drawdown_after, subsequent_return, ex_post_return,
forward_4h, fwd_ret, t_plus_8, settlement_price, final_move, move_realized).
It ALSO over-blocked the legitimate present-tense feed fields 'resolution' and
'label', deleting real evidence.

This test pins both directions: outcome concepts are blocked, present-tense facts survive.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fia_brain.evidence import _future_semantic_path as F, prediction_time_violations
from fia_brain.util import sha256_obj

MUST_BLOCK = [
    # V6.6.1 known set
    "nq_4h", "nq_8h", "move_4h_pct", "move_8h_pct", "actual_4h", "actual_8h",
    "correct_4h", "correct_8h", "future_price_8h", "outcome_direction",
    "mfe_pct", "mae_pct",
    # aliases the V6.6.1 detector missed
    "settled_direction", "verified_move", "post_move_pct", "eod_close",
    "close_after_8h", "px_t_plus_4h", "y_true", "label_direction", "was_correct",
    "hit_target", "excursion", "drawdown_after", "subsequent_return",
    "ex_post_return", "forward_4h", "fwd_ret", "t_plus_8", "resolved_at_price",
    "settlement_price", "final_move", "move_realized", "target_close_8h",
    "realized_return_4h", "next_close", "forward_return_8h", "hindsight_bias",
    "lookahead_return", "runup_after_entry",
    # nested paths
    "backtest.predictions[0].actual_8h", "live.forecast.realized_return_4h",
]

MUST_ALLOW = [
    "macro.cpi.actual", "fed.target_rate", "realized_volatility_30d",
    "earnings.actual_eps", "next_fomc_date", "upcoming_earnings",
    "analyst.target_price", "consensus_target_price",
    "live.snapshot.resolution", "candles.resolution", "live.forecast.label",
    "nq_structure", "nq_structure_last_bar_end_utc", "liquidity.asia_high",
    "provider_health.score", "live.forecast.bullish_probability",
    "news.headline", "semis.nvda.change_percent", "session.london_high",
    "dxy.value", "us10y.value", "earnings_calendar.next_report_date",
    "live.cognitive.reliability_score", "live.forecast.confidence",
]

missed = [p for p in MUST_BLOCK if not F(p)]
assert not missed, "outcome aliases NOT blocked: %r" % (missed,)

false_pos = [p for p in MUST_ALLOW if F(p)]
assert not false_pos, "legitimate present-tense fields wrongly blocked: %r" % (false_pos,)

# End-to-end through the ledger scanner.
def ledger(paths):
    recs = []
    for i, p in enumerate(paths, 1):
        body = {"source": "/api/dashboard", "path": p, "value": 1.0}
        r = dict(body); r["record_hash"] = sha256_obj(body); r["evidence_id"] = "E%04d" % i
        recs.append(r)
    led = {"snapshot_sha256": "x", "record_count": len(recs), "records": recs}
    led["ledger_sha256"] = sha256_obj({k: v for k, v in led.items()})
    return led

v = prediction_time_violations(ledger(["nq_structure", "settled_direction", "dxy.value"]))
assert v == ["settled_direction"], v
assert prediction_time_violations(ledger(MUST_ALLOW)) == []
assert sorted(prediction_time_violations(ledger(MUST_BLOCK))) == sorted(set(MUST_BLOCK))

print("PASS test_future_semantic_aliases_v662")
