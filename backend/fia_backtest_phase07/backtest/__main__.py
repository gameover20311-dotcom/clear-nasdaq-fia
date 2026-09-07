from .sessions import classify_session


def main():
    examples = [
        "2026-08-31T02:00:00+00:00",
        "2026-08-31T10:00:00+00:00",
        "2026-08-31T15:00:00+00:00",
        "2026-08-31T22:00:00+00:00",
    ]

    for timestamp in examples:
        print(f"{timestamp} -> {classify_session(timestamp)}")


if __name__ == "__main__":
    main()
