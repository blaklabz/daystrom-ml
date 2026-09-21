import csv
from dataclasses import asdict
from pathlib import Path

from daystrom.features import (
    FeatureWindow,
    bucket_events,
    extract_sable_features,
)
from daystrom.loki import LokiClient


DEFAULT_DATASET_PATH = Path("datasets/sable_features.csv")


def build_sable_dataset(
    hours: float = 24,
    window_minutes: int = 5,
) -> list[FeatureWindow]:
    """
    Build feature windows from Sable telemetry stored in Loki.
    """

    client = LokiClient()

    events = client.query_events_since(
        '{app="sable"}',
        hours=hours,
    )

    buckets = bucket_events(
        events,
        window_minutes=window_minutes,
    )

    dataset = []

    for window_start in sorted(buckets):
        features = extract_sable_features(
            buckets[window_start],
            window_start,
        )

        if features is not None:
            dataset.append(features)

    return dataset


def write_dataset_csv(
    dataset: list[FeatureWindow],
    path: Path = DEFAULT_DATASET_PATH,
) -> None:
    """
    Write feature windows to a CSV dataset.
    """

    if not dataset:
        return

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    for feature_window in dataset:
        row = asdict(feature_window)

        row["window_start"] = (
            feature_window.window_start.isoformat()
        )

        rows.append(row)

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=rows[0].keys(),
        )

        writer.writeheader()
        writer.writerows(rows)
