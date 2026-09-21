from daystrom.features import (
    FeatureWindow,
    bucket_events,
    extract_sable_features,
)
from daystrom.loki import LokiClient


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
