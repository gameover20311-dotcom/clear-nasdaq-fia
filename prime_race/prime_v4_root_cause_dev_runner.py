from __future__ import annotations

import json
from typing import Any

import prime_v4_root_cause_dev as dev


def _stringify_mapping_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            ("ABSTAIN" if key is None else str(key)): _stringify_mapping_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_stringify_mapping_keys(item) for item in value]
    if isinstance(value, tuple):
        return [_stringify_mapping_keys(item) for item in value]
    return value


def canonical_without_mixed_key_failure(obj: Any) -> bytes:
    normalized = _stringify_mapping_keys(obj)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


# HARNESS-ONLY repair: preserve experiment/model/tasks/prompts/scoring;
# normalize report mapping keys before hashing so None + string keys serialize.
dev.canonical = canonical_without_mixed_key_failure


if __name__ == "__main__":
    dev.main()
