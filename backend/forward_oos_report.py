#!/usr/bin/env python3
from __future__ import annotations
import json
from fia.forward_oos import DEFAULT_ROOT, forward_report

if __name__ == "__main__":
    print(json.dumps(forward_report(DEFAULT_ROOT), indent=2, ensure_ascii=False))
