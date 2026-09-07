from pathlib import Path

from fia_backtest_phase13.backtest.integration import integrate_dataset


def main():
    root = Path.cwd()

    source = (
        root
        / "fia_backtest_phase13"
        / "data"
        / "historical_predictions.csv"
    )

    destination = (
        root
        / "fia_backtest_phase13"
        / "data"
        / "validated_historical_predictions.csv"
    )

    result = integrate_dataset(source, destination)

    print(f"source_exists={source.exists()}")
    print(f"records_read={result['records_read']}")
    print(
        f"dataset_valid="
        f"{result['validation']['valid']}"
    )
    print(
        f"invalid_records="
        f"{result['validation']['invalid_records']}"
    )
    print(f"written={result['written']}")

    if not source.exists():
        print(
            "READY: place the real historical prediction/outcome CSV at:"
        )
        print(source)


if __name__ == "__main__":
    main()
