"""Read-only Loki client for Daystrom telemetry and source discovery."""

import os
from datetime import datetime, timedelta, timezone

import httpx

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

    def _get(self, endpoint: str, *, params: dict | list[tuple] | None = None) -> dict:
        response = httpx.get(
            f"{self.base_url}/loki/api/v1/{endpoint}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError(f"Loki {endpoint} request failed: {payload}")
        return payload

    @staticmethod
    def _window_ns(hours: float) -> tuple[int, int]:
        if hours <= 0:
            raise ValueError("hours must be greater than zero")
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        return int(start.timestamp() * 1_000_000_000), int(end.timestamp() * 1_000_000_000)

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
        return self._get("query_range", params=params)

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
                events.append(TelemetryEvent.from_loki(labels, timestamp_ns, message))
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
        start, end = self._window_ns(hours)
        return self.query_events(
            query,
            start=start,
            end=end,
            limit=limit,
            direction="forward",
        )

    def discover_streams(self, *, hours: float = 24) -> list[dict[str, str]]:
        """Discover stream label sets without hardcoding host/app/job names.

        This reports streams observed in the window, not host health.
        """
        start, end = self._window_ns(hours)
        labels = self._get("labels", params={"start": start, "end": end})["data"]
        if not labels:
            return []
        # Loki treats multiple match[] selectors as a union.
        params = [("match[]", f'{{{label}=~".+"}}') for label in labels]
        params.extend([("start", start), ("end", end)])
        streams = self._get("series", params=params)["data"]
        return sorted(streams, key=lambda stream: tuple(sorted(stream.items())))

    def discover_hosts(self, *, hours: float = 24) -> list[str]:
        """Return hosts represented by Loki streams in the requested window."""
        return sorted({
            stream["host"]
            for stream in self.discover_streams(hours=hours)
            if stream.get("host")
        })
