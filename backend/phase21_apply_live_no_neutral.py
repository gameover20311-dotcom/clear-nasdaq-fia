from pathlib import Path
import shutil
import py_compile

ENGINE = Path("fia/engine.py")
BACKUP = Path("fia/engine.before_phase21_no_neutral.py")

OLD = '''    if bullish_probability >= 55:
        direction = "BULLISH"
    elif bullish_probability <= 45:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"
'''

NEW = '''    # Phase 21 validated decision policy:
    # remove the 55/45 prediction neutral band.
    # Use the same one-decimal probability exposed by the FIA result/UI
    # so the displayed probability and direction cannot disagree around 50%.
    decision_probability = round(bullish_probability, 1)

    if decision_probability >= 50.0:
        direction = "BULLISH"
    else:
        direction = "BEARISH"
'''


def main():
    if not ENGINE.exists():
        raise SystemExit(f"Missing live engine: {ENGINE}")

    source = ENGINE.read_text(encoding="utf-8")

    if NEW in source:
        print("=== PHASE 21 LIVE PATCH ===")
        print("status = ALREADY_APPLIED")
        print("engine =", ENGINE)
        print("=== COMPLETE ===")
        return

    count = source.count(OLD)

    if count != 1:
        raise SystemExit(
            "Safety stop: expected exactly one 55/45 decision block "
            f"in {ENGINE}, found {count}. Live engine was NOT changed."
        )

    if not BACKUP.exists():
        shutil.copy2(ENGINE, BACKUP)

    patched = source.replace(OLD, NEW, 1)

    # Syntax-check patched text before writing over live engine.
    compile(patched, str(ENGINE), "exec")

    ENGINE.write_text(patched, encoding="utf-8")

    # Compile the actual written file too.
    py_compile.compile(
        str(ENGINE),
        doraise=True,
    )

    print("=== PHASE 21 LIVE PATCH ===")
    print("status = APPLIED")
    print("engine =", ENGINE)
    print("backup =", BACKUP)
    print(
        "decision_policy = "
        "round(bullish_probability, 1) >= 50.0 => BULLISH; else BEARISH"
    )
    print("weights_changed = NO")
    print("probability_model_changed = NO")
    print("confidence_model_changed = NO")
    print("signals_changed = NO")
    print("=== COMPLETE ===")


if __name__ == "__main__":
    main()
