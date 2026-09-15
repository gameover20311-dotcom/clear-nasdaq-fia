from __future__ import annotations

import json
import os

# LOCAL_OLLAMA is the only mode this helper enables. It makes no paid API calls.
os.environ["ARENA_BILLING_MODE"] = "FREE_ONLY_CONFIRMED"
os.environ["ARENA_PROVIDER"] = "LOCAL_OLLAMA"
os.environ.setdefault("ARENA_MODEL", "gpt-oss:20b")
os.environ.setdefault("ARENA_TASK_LIMIT", "4")
os.environ.setdefault("ARENA_TIMEOUT_SECONDS", "90")
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# Importing the hardening layer installs V3 over the isolated arena module.
from prime_race import zero_budget_hardening as hardening  # noqa: E402

if __name__ == "__main__":
    result = hardening.arena._execute_arena()
    print(json.dumps(result, indent=2, sort_keys=True))
