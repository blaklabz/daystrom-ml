import os

import httpx


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
