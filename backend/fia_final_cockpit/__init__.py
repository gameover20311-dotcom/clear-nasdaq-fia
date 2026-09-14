__version__ = "1.0.0"

try:
    from .autorun import start as _start_gptoss_autorun
    _start_gptoss_autorun()
except Exception as _gptoss_autorun_bootstrap_error:
    print(
        "GPTOSS_AUTORUN_BOOTSTRAP_ERROR",
        type(_gptoss_autorun_bootstrap_error).__name__ + ": " + str(_gptoss_autorun_bootstrap_error)[:300],
        flush=True,
    )
