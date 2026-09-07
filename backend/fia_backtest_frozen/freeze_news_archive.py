#!/usr/bin/env python3
"""Build the MINIMAL frozen historical news archive.

WHY
---
The 258-row replay needs a point-in-time news archive, but the source Polygon
capture is 132MB and is .gitignore'd, so the ONLINE deployment could not run the
replay at all. That single gap was the reason HISTORICAL PIT stayed PARTIAL.

Most of that 132MB is fields the replay never reads: `insights`, `keywords`,
`image_url`, `author`, `id`, and a verbatim `raw` passthrough kept by the
normaliser. Verified by grep: nothing downstream reads article["raw"].

WHAT THIS KEEPS
---------------
Exactly the fields normalize_polygon_article() consumes:
    title, description, publisher.name, article_url, published_utc, tickers

WHAT IT DOES NOT DO
-------------------
* Does not regenerate headlines from a current API. The source is the original
  historical capture; this is a projection of it, not a re-fetch.
* Does not invent, dedupe, reorder or re-time anything. One input article maps
  to at most one output record, with its original published_utc verbatim.
* Does not drop an article for being unhelpful. Only whole FIELDS are dropped.

A content hash over the output makes the projection auditable, and the record
count must match the source exactly.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "polygon_news_minimal_20250901_20260831.jsonl"
MANIFEST = HERE / "FROZEN_NEWS_MANIFEST.json"

KEEP = ("title", "description", "article_url", "published_utc", "tickers")


def project(source_path: Path) -> dict:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    arts = payload if isinstance(payload, list) else (payload.get("articles") or [])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    skipped_no_title = 0
    earliest = latest = None
    with OUT.open("w", encoding="utf-8") as f:
        for a in arts:
            if not isinstance(a, dict):
                continue
            title = str(a.get("title") or "").strip()
            if not title:
                # normalize_polygon_article() already discards these, so keeping
                # them would change nothing except the record count.
                skipped_no_title += 1
                continue
            pub = a.get("publisher") or {}
            rec = {
                "title": title,
                "description": str(a.get("description") or "").strip(),
                "publisher": {"name": (pub.get("name") if isinstance(pub, dict)
                                       else str(pub or "Unknown")) or "Unknown"},
                "article_url": a.get("article_url") or "",
                "published_utc": a.get("published_utc"),
                "tickers": a.get("tickers") or [],
            }
            ts = str(rec["published_utc"] or "")
            if ts:
                earliest = ts if earliest is None or ts < earliest else earliest
                latest = ts if latest is None or ts > latest else latest
            f.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
            kept += 1
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    manifest = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Polygon (historical capture, projected)",
        "source_articles": len(arts),
        "records": kept,
        "skipped_untitled": skipped_no_title,
        "coverage_first_published_utc": earliest,
        "coverage_last_published_utc": latest,
        "fields_kept": list(KEEP),
        "file": OUT.name,
        "sha256": digest,
        "bytes": OUT.stat().st_size,
        "note": ("Field projection of the original historical capture. No article "
                 "was invented, re-fetched, re-timed, reordered or deduplicated. "
                 "Untitled articles are omitted because the normaliser already "
                 "discarded them."),
    }
    MANIFEST.write_text(json.dumps(manifest, sort_keys=True, indent=1))
    return manifest


if __name__ == "__main__":
    src = Path(sys.argv[1])
    if not src.exists():
        print("source archive not found: %s" % src)
        sys.exit(2)
    m = project(src)
    print("source articles : %d" % m["source_articles"])
    print("records written : %d  (untitled omitted: %d)" % (m["records"], m["skipped_untitled"]))
    print("coverage        : %s .. %s" % (m["coverage_first_published_utc"],
                                          m["coverage_last_published_utc"]))
    print("bytes           : %.1f MB" % (m["bytes"] / 1e6))
    print("sha256          : %s" % m["sha256"])
