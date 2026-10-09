"""Read-only Loki host activity snapshots.

A recent log proves only that Loki has an event for the host; it does not
prove that the host is healthy or that its log collector is currently working.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from daystrom.loki import LokiClient


@dataclass(frozen=True)
class HostActivity:
    host: str
    last_event: datetime | None
    age_seconds: float | None
    labels: dict[str, str]
    status: str


def _ns(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000_000)


def snapshot_hosts(
    client: LokiClient | None = None,
    *,
    discovery_hours: float = 24,
    lookback_hours: float = 24,
) -> list[HostActivity]:
    """Find hosts and their latest event within a bounded lookback.

    Statuses are OBSERVED (event found) and NO_RECENT_EVENT. Neither is a
    health verdict. Historical inventory and silence baselines come later.
    """
    if discovery_hours <= 0 or lookback_hours <= 0:
        raise ValueError("discovery_hours and lookback_hours must be positive")

    client = client or LokiClient()
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=lookback_hours)
    hosts = client.discover_hosts(hours=discovery_hours)
    results = []

    for host in hosts:
        # Quote/escape label values safely for LogQL string literals.
        escaped_host = host.replace('\\', '\\\\').replace('"', '\\"')
        events = client.query_events(
            f'{{host="{escaped_host}"}}',
            start=_ns(start),
            end=_ns(now),
            limit=1,
            direction="backward",
        )
        if events:
            latest = events[0]
            results.append(HostActivity(
                host=host,
                last_event=latest.timestamp,
                age_seconds=max(0.0, (now - latest.timestamp).total_seconds()),
                labels=dict(latest.labels),
                status="OBSERVED",
            ))
        else:
            results.append(HostActivity(
                host=host,
                last_event=None,
                age_seconds=None,
                labels={},
                status="NO_RECENT_EVENT",
            ))

    return results


def main() -> None:
    client = LokiClient()
    activities = snapshot_hosts(client)
    print(f"{'HOST':<24} {'STATUS':<17} {'AGE':>12}  LAST EVENT (UTC)")
    print("-" * 83)
    for item in activities:
        age = f"{item.age_seconds:.0f}s" if item.age_seconds is not None else "-"
        last = item.last_event.isoformat() if item.last_event else "-"
        print(f"{item.host:<24} {item.status:<17} {age:>12}  {last}")
    print(f"\n{len(activities)} hosts; status indicates log observation, not host health.")


if __name__ == "__main__":
    main()
