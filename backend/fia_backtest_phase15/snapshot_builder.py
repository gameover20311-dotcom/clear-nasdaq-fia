from .snapshot_schema import build_snapshot
from .historical_market import get_historical_nq_price


async def build_historical_snapshot(timestamp, raw_data=None):
    raw_data = dict(raw_data or {})

    nq_price = await get_historical_nq_price(timestamp)

    if nq_price is not None:
        raw_data["nq_futures_price"] = nq_price

    return build_snapshot(
        raw_data=raw_data,
        timestamp=timestamp,
    )


if __name__ == "__main__":
    print("FIA Phase 15 Snapshot Builder: READY")
