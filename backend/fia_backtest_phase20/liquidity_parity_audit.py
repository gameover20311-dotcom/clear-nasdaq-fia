from collections import Counter
from datetime import datetime, timedelta, timezone

from fia.providers import ProviderHub
from fia_backtest_phase19.full_snapshot import (
    liquidity_asof as phase19_liquidity_asof,
)
from fia_backtest_phase20.liquidity_pti import (
    liquidity_asof_cached,
)

START = datetime(
    2026,
    7,
    1,
    17,
    0,
    tzinfo=timezone.utc,
)
END = datetime(
    2026,
    8,
    31,
    17,
    0,
    tzinfo=timezone.utc,
)


def checkpoints():
    current = START

    while current <= END:
        if current.weekday() < 5:
            yield current

        current += timedelta(days=1)


def main():
    hub = ProviderHub()

    total = 0
    comparable = 0
    direction_same = 0
    signal_same = 0

    old_missing = 0
    new_missing = 0

    selected_contracts = Counter()
    mismatches = []

    print(
        "=== PHASE 20 LIQUIDITY PARITY AUDIT ==="
    )

    for target in checkpoints():
        old = phase19_liquidity_asof(
            target,
            hub,
        )

        new = liquidity_asof_cached(
            target,
            hub,
        )

        total += 1

        old_direction = old.get(
            "liquidity_direction"
        )
        new_direction = new.get(
            "liquidity_direction"
        )

        old_signal = old.get(
            "liquidity_signal"
        )
        new_signal = new.get(
            "liquidity_signal"
        )

        if old_signal is None:
            old_missing += 1

        if new_signal is None:
            new_missing += 1

        contract = new.get(
            "liquidity_contract"
        )

        if contract:
            selected_contracts[
                contract
            ] += 1

        if (
            old_signal is not None
            and new_signal is not None
        ):
            comparable += 1

            if (
                old_direction
                == new_direction
            ):
                direction_same += 1

            if float(old_signal) == float(
                new_signal
            ):
                signal_same += 1

            if (
                old_direction
                != new_direction
            ):
                mismatches.append(
                    {
                        "date": (
                            target.date()
                            .isoformat()
                        ),
                        "old": old_direction,
                        "new": new_direction,
                        "contract": contract,
                        "old_price": (
                            old.get("nq_price")
                        ),
                        "new_price": (
                            new.get("nq_price")
                        ),
                    }
                )

    direction_alignment = (
        100.0
        * direction_same
        / comparable
        if comparable
        else 0.0
    )

    signal_alignment = (
        100.0
        * signal_same
        / comparable
        if comparable
        else 0.0
    )

    print()
    print("=== PARITY SUMMARY ===")
    print("checkpoints =", total)
    print(
        "comparable =",
        comparable,
    )
    print(
        "phase19 missing =",
        old_missing,
    )
    print(
        "phase20 missing =",
        new_missing,
    )
    print(
        "direction alignment =",
        round(
            direction_alignment,
            2,
        ),
        "%",
    )
    print(
        "signal alignment =",
        round(
            signal_alignment,
            2,
        ),
        "%",
    )
    print(
        "selected contracts =",
        dict(selected_contracts),
    )

    print()
    print(
        "=== DIRECTION MISMATCHES ==="
    )

    for row in mismatches[:20]:
        print(
            row["date"],
            "| Phase19 =",
            row["old"],
            "| Phase20 =",
            row["new"],
            "| contract =",
            row["contract"],
            "| old_price =",
            row["old_price"],
            "| new_price =",
            row["new_price"],
        )

    if len(mismatches) > 20:
        print(
            "... additional mismatches =",
            len(mismatches) - 20,
        )

    print()
    print(
        "=== AUDIT VERDICT INPUT ==="
    )

    if (
        comparable >= 40
        and direction_alignment >= 80.0
    ):
        verdict = (
            "PASS_STRONG_PARITY"
        )
    elif (
        comparable >= 35
        and direction_alignment >= 65.0
    ):
        verdict = (
            "PASS_USABLE_WITH_DOCUMENTED_PROVIDER_DIFFERENCE"
        )
    else:
        verdict = (
            "REVIEW_BEFORE_PHASE20_BACKTEST"
        )

    print("verdict =", verdict)
    print(
        "=== PHASE 20 LIQUIDITY PARITY AUDIT COMPLETE ==="
    )


if __name__ == "__main__":
    main()
