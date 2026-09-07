def _pct(current, previous):
    if current is None or previous is None:
        return None
    if previous == 0:
        return None
    return ((float(current) - float(previous)) / float(previous)) * 100.0


def _normalize_move(move, scale=1.0):
    """
    Convert percentage market movement into FIA's normalized
    directional score [-1, +1].

    Example:
        +1.0% move -> +1.0
        -1.0% move -> -1.0
        +0.2% move -> +0.2
    """
    if move is None:
        return None

    value = float(move) / float(scale)

    if value > 1.0:
        return 1.0
    if value < -1.0:
        return -1.0

    return value


def adapt_market_snapshot(s):
    nq_move = _pct(s.get("nq"), s.get("nq_prev"))
    spx_move = _pct(s.get("spx"), s.get("spx_prev"))
    dxy_move = _pct(s.get("dxy"), s.get("dxy_prev"))
    us10y_move = _pct(s.get("us10y"), s.get("us10y_prev"))
    nvda_move = _pct(s.get("nvda"), s.get("nvda_prev"))
    amd_move = _pct(s.get("amd"), s.get("amd_prev"))
    qqq_move = _pct(s.get("qqq"), s.get("qqq_prev"))

    return {
        "status": "HISTORICAL",
        "symbol": "QQQ",
        "data": {
            "nq_futures_price": s.get("nq"),
            "price": s.get("qqq"),

            "nq_structure": _normalize_move(nq_move),
            "spx_confirmation": _normalize_move(spx_move),
            "dxy": _normalize_move(-dxy_move),
            "us10y": _normalize_move(-us10y_move),
            "mega_cap": _normalize_move(nvda_move),
            "semis": _normalize_move(amd_move),
            "breadth": _normalize_move(qqq_move),

            "news": 0.0,
            "macro": 0.0,
            "earnings": 0.0,
        },
    }


if __name__ == "__main__":
    print("FIA Phase 15 Signal Adapter: READY")
