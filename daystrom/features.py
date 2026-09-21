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
TOOL_CALLS_PATTERN = re.compile(r"\btool_calls=(\d+)\b")


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

    generation_events = [
        event
        for event in events
        if event.app == "sable"
        and event.log_type == "llm"
        and "Generation completed" in event.message
    ]

    memory_evaluation_events = [
        event
        for event in events
        if event.app == "sable"
        and event.log_type == "memory"
        and "Background memory processing completed"
        in event.message
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

    generation_latencies_ms = []
    tool_call_count = 0

    for event in generation_events:
        elapsed_match = ELAPSED_PATTERN.search(
            event.message
        )

        if elapsed_match:
            generation_latencies_ms.append(
                float(elapsed_match.group(1)) * 1000
            )

        tool_calls_match = TOOL_CALLS_PATTERN.search(
            event.message
        )

        if tool_calls_match:
            tool_call_count += int(
                tool_calls_match.group(1)
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
        llm_generation_count=len(generation_events),
        avg_generation_ms=(
            sum(generation_latencies_ms)
            / len(generation_latencies_ms)
            if generation_latencies_ms
            else 0.0
        ),
        memory_evaluation_count=len(
            memory_evaluation_events
        ),
        tool_call_count=tool_call_count,
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
