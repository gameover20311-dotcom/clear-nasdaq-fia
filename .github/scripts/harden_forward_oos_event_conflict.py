#!/usr/bin/env python3
from pathlib import Path

p = Path('backend/fia/forward_oos_durable.py')
s = p.read_text(encoding='utf-8')
marker = 'EVENT_MIRROR_CONFLICT'
if marker in s:
    print('event conflict hardening already present')
    raise SystemExit(0)
needle = '''                _mirror_evidence_tx(cur, cid, event, evidence)\n'''
replacement = '''                # ON CONFLICT must never turn a different event at the same\n                # scientific sequence into a false success. Re-read the row and\n                # prove the durable bytes/identity are exactly the event being\n                # mirrored before evidence/head writes may continue.\n                cur.execute(\n                    "SELECT event_type, forecast_id, created_at_utc, prev_event_hash, "\n                    "event_hash, file_name, canonical_json, is_test "\n                    "FROM forward_oos_events WHERE campaign_id=%s AND seq=%s",\n                    (cid, int(event.get("seq") or 0)))\n                existing_event = cur.fetchone() or {}\n                expected_event = {\n                    "event_type": str(event.get("event_type") or ""),\n                    "forecast_id": str(event.get("forecast_id") or ""),\n                    "created_at_utc": str(event.get("created_at_utc") or ""),\n                    "prev_event_hash": str(event.get("prev_event_hash") or ""),\n                    "event_hash": str(event.get("event_hash") or ""),\n                    "file_name": str(file_name),\n                    "canonical_json": bytes(canonical),\n                    "is_test": bool(is_test),\n                }\n                observed_event = {\n                    "event_type": str(existing_event.get("event_type") or ""),\n                    "forecast_id": str(existing_event.get("forecast_id") or ""),\n                    "created_at_utc": str(existing_event.get("created_at_utc") or ""),\n                    "prev_event_hash": str(existing_event.get("prev_event_hash") or ""),\n                    "event_hash": str(existing_event.get("event_hash") or ""),\n                    "file_name": str(existing_event.get("file_name") or ""),\n                    "canonical_json": bytes(existing_event.get("canonical_json") or b""),\n                    "is_test": bool(existing_event.get("is_test")),\n                }\n                if observed_event != expected_event:\n                    raise RuntimeError("EVENT_MIRROR_CONFLICT")\n                _mirror_evidence_tx(cur, cid, event, evidence)\n'''
if needle not in s:
    raise SystemExit('target mirror_event anchor not found; refusing fuzzy patch')
s = s.replace(needle, replacement, 1)
p.write_text(s, encoding='utf-8')
print('patched Forward-OOS event conflict verification')
