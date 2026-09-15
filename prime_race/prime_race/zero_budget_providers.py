from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_target = Path(__file__).resolve().parents[1] / "zero_budget_providers.py"
_name = "prime_zero_budget_provider_impl"
_spec = importlib.util.spec_from_file_location(_name, _target)
if _spec is None or _spec.loader is None:
    raise ImportError("zero_budget_providers implementation not loadable")
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_name] = _mod
_spec.loader.exec_module(_mod)

ProviderConfig = _mod.ProviderConfig
ProviderError = _mod.ProviderError
call_free_provider = _mod.call_free_provider

__all__ = ["ProviderConfig", "ProviderError", "call_free_provider"]
