from datetime import datetime, timezone


TIMESTAMP_FIELDS = (
    "datetime",
    "publishedAt",
    "published_at",
    "timestamp",
    "time",
)


def normalize_timestamp(value):
    if isinstance(value, (int, float)):
        if value > 100000000000:
            value /= 1000.0
        return datetime.fromtimestamp(
            value,
            tz=timezone.utc,
        )

    if isinstance(value, str):
        value = value.strip()

        try:
            numeric = float(value)
            if numeric > 100000000000:
                numeric /= 1000.0
            return datetime.fromtimestamp(
                numeric,
                tz=timezone.utc,
            )
        except ValueError:
            pass

        value = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    raise ValueError("Unsupported timestamp")


def filter_news_point_in_time(
    articles,
    target_timestamp,
):
    target = normalize_timestamp(target_timestamp)
    result = []

    for article in articles:
        timestamp = None

        for field in TIMESTAMP_FIELDS:
            if article.get(field) is not None:
                timestamp = article.get(field)
                break

        if timestamp is None:
            continue

        try:
            published = normalize_timestamp(timestamp)
        except (TypeError, ValueError):
            continue

        if published <= target:
            result.append(article)

    return result


if __name__ == "__main__":
    print("FIA Phase 15 Historical News Filter: READY")
