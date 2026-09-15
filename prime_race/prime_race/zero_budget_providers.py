from __future__ import annotations

import importlib.util
from pathlib import Path

_target = Path(__file__).resolve().parents[1] / "zero_budget_providers.py"
_spec = importlib.util.spec_from_file_location("prime_zero_budget_provider_impl", _target)
if _spec is None or _spec.loader is None:
    raise ImportError("zero_budget_providers implementation not loadable")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ProviderConfig = _mod.ProviderConfig
ProviderError = _mod.ProviderError
call_free_provider = _mod.call_free_provider

__all__ = ["ProviderConfig", "ProviderError", "call_free_provider"]
