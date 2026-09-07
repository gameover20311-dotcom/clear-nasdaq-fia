from datetime import datetime, timezone


def normalize_timestamp(timestamp):
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def filter_point_in_time(records, timestamp):
    target = normalize_timestamp(timestamp)

    filtered = []

    for record in records:
        record_time = record.get("timestamp") or record.get("published_at")
        if not record_time:
            continue

        try:
            record_dt = normalize_timestamp(record_time)
        except (TypeError, ValueError):
            continue

        if record_dt <= target:
            filtered.append(record)

    return filtered


if __name__ == "__main__":
    print("FIA Phase 15 Point-in-Time Filter: READY")
