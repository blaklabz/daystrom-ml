from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class TelemetryEvent:
    timestamp_ns: int
    timestamp: datetime
    host: str | None
    app: str | None
    log_type: str | None
    message: str

    @classmethod
    def from_loki(
        cls,
        labels: dict,
        timestamp_ns: str,
        message: str,
    ) -> "TelemetryEvent":
        timestamp_ns_int = int(timestamp_ns)

        return cls(
            timestamp_ns=timestamp_ns_int,
            timestamp=datetime.fromtimestamp(
                timestamp_ns_int / 1_000_000_000,
                tz=timezone.utc,
            ),
            host=labels.get("host"),
            app=labels.get("app"),
            log_type=labels.get("log_type"),
            message=message,
        )
