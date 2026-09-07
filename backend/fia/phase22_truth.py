# PHASE22_TRUTH_CONSISTENCY_V1
from __future__ import annotations


def validate_truth(*, direction, thesis, bullish_probability, bearish_probability, signals, raw, liquidity_groups=None):
    direction = str(direction or "").upper()
    thesis_text = str(thesis or "").lower()
    expected_word = "bullish" if direction == "BULLISH" else "bearish"

    checks = {}
    checks["probability_sum_100"] = abs(
        float(bullish_probability) + float(bearish_probability) - 100.0
    ) <= 0.11
    checks["direction_thesis_match"] = expected_word in thesis_text

    news = raw.get("news")
    articles = int(raw.get("news_articles") or 0)
    scored = int(raw.get("news_scored_articles") or 0)
    news_status = str(raw.get("news_status") or "missing")
    checks["news_truth"] = (
        (news is None and scored == 0)
        or (news is not None and articles > 0 and scored > 0 and news_status == "live_scored")
    )

    missing = [s for s in signals if str(getattr(s, "freshness", "")).lower() == "missing"]
    checks["missing_signals_marked"] = all(
        "awaiting provider data" in str(getattr(s, "detail", "")).lower()
        for s in missing
    )

    if liquidity_groups:
        qqq = liquidity_groups.get("qqq", {})
        nq = liquidity_groups.get("nq", {})
        checks["liquidity_instruments_separate"] = (
            qqq.get("instrument") == "QQQ" and nq.get("instrument") == "NQ"
        )
    else:
        checks["liquidity_instruments_separate"] = True

    return {"pass": all(checks.values()), "checks": checks}
