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

from prime_race.zero_budget_arena import _execute_arena  # noqa: E402

if __name__ == "__main__":
    result = _execute_arena()
    print(json.dumps(result, indent=2, sort_keys=True))
