import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from daystrom.telemetry import TelemetryEvent


@dataclass
class FeatureWindow:
    window_start: datetime
    host: str
    app: str

    request_count: int = 0
    error_count: int = 0

    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0

    llm_generation_count: int = 0
    avg_generation_ms: float = 0.0

    memory_evaluation_count: int = 0
    memory_creation_count: int = 0

    tool_call_count: int = 0


ELAPSED_PATTERN = re.compile(r"\belapsed=([0-9.]+)s\b")


def extract_sable_features(
    events: list[TelemetryEvent],
    window_start: datetime,
) -> FeatureWindow | None:
    response_events = [
        event
        for event in events
        if event.app == "sable"
        and event.log_type == "api"
        and "Chat response ready" in event.message
    ]

    if not response_events:
        return None

    latencies_ms = []

    for event in response_events:
        match = ELAPSED_PATTERN.search(event.message)

        if match:
            latencies_ms.append(
                float(match.group(1)) * 1000
            )

    return FeatureWindow(
        window_start=window_start,
        host=response_events[0].host or "unknown",
        app="sable",
        request_count=len(response_events),
        avg_latency_ms=(
            sum(latencies_ms) / len(latencies_ms)
            if latencies_ms
            else 0.0
        ),
        max_latency_ms=(
            max(latencies_ms)
            if latencies_ms
            else 0.0
        ),
    )


def bucket_events(
    events: list[TelemetryEvent],
    window_minutes: int = 5,
) -> dict[datetime, list[TelemetryEvent]]:
    buckets = defaultdict(list)

    for event in events:
        timestamp = event.timestamp

        bucket_minute = (
            timestamp.minute // window_minutes
        ) * window_minutes

        window_start = timestamp.replace(
            minute=bucket_minute,
            second=0,
            microsecond=0,
        )

        buckets[window_start].append(event)

    return dict(buckets)
