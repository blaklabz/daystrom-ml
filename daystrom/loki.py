import os

import httpx

from datetime import datetime, timedelta, timezone
from daystrom.telemetry import TelemetryEvent


DEFAULT_LOKI_URL = "http://loki.blaklabz.io:3100"


class LokiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
    ):
        self.base_url = (
            base_url
            or os.getenv("LOKI_URL")
            or DEFAULT_LOKI_URL
        ).rstrip("/")

        self.timeout = timeout


    def query_range(
        self,
        query: str,
        *,
        start: int | None = None,
        end: int | None = None,
        limit: int = 100,
        direction: str = "backward",
    ) -> dict:
        params = {
            "query": query,
            "limit": limit,
            "direction": direction,
        }

        if start is not None:
            params["start"] = start

        if end is not None:
            params["end"] = end

        response = httpx.get(
            f"{self.base_url}/loki/api/v1/query_range",
            params=params,
            timeout=self.timeout,
        )

        response.raise_for_status()

        payload = response.json()

        if payload.get("status") != "success":
            raise RuntimeError(
                f"Loki query failed: {payload}"
            )

        return payload

    def query_events(
        self,
        query: str,
        *,
        start: int | None = None,
        end: int | None = None,
        limit: int = 100,
        direction: str = "backward",
    ) -> list[TelemetryEvent]:
        payload = self.query_range(
            query,
            start=start,
            end=end,
            limit=limit,
            direction=direction,
        )

        events = []

        for stream in payload["data"]["result"]:
            labels = stream["stream"]

            for timestamp_ns, message in stream["values"]:
                events.append(
                    TelemetryEvent.from_loki(
                        labels,
                        timestamp_ns,
                        message,
                    )
                )

        events.sort(
            key=lambda event: event.timestamp_ns,
            reverse=(direction == "backward"),
        )

        return events

    def query_events_since(
        self,
        query: str,
        *,
        hours: float = 24,
        limit: int = 5000,
    ) -> list[TelemetryEvent]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)

        return self.query_events(
            query,
            start=int(start.timestamp() * 1_000_000_000),
            end=int(end.timestamp() * 1_000_000_000),
            limit=limit,
            direction="forward",
        )
