"""Persist Loki event counts for known sources over aligned five-minute windows.

Run: python -m daystrom.event_volume
Currently host-level only. Other source types can use the same table later.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from daystrom.db import get_session_factory
from daystrom.loki import LokiClient
from daystrom.models import EventVolumeObservation, Source

WINDOW_SECONDS = 300

@dataclass(frozen=True)
class VolumeSummary:
    window_start: datetime
    window_end: datetime
    known_hosts: int
    hosts_with_events: int
    observations_inserted: int
    total_events: int

def collect_host_volume(client: LokiClient | None = None, *, at: datetime | None = None) -> VolumeSummary:
    """Record one count per inventoried host. Query failure means no DB writes.

    The latest completed aligned five-minute window is used. A retry of
    the same window is idempotent (ON CONFLICT DO NOTHING).
    """
    client = client or LokiClient()
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("at must be timezone-aware")
    end_epoch = int(now.timestamp()) // WINDOW_SECONDS * WINDOW_SECONDS
    end = datetime.fromtimestamp(end_epoch, tz=timezone.utc)
    start = end - timedelta(seconds=WINDOW_SECONDS)

    # Fetch metrics before any writes. The result may omit hosts with zero events.
    expression = 'sum by (host) (count_over_time({host=~".+"}[5m]))'
    payload = client.query_instant(expression, at=end)
    counts: dict[str, int] = {}
    for row in payload["data"]["result"]:
        host = row.get("metric", {}).get("host")
        if not host:
            raise ValueError("Loki returned a result without a host label")
        value = float(row["value"][1])
        if not value.is_integer() or value < 0:
            raise ValueError(f"Invalid Loki event count for {host}: {value}")
        if host in counts:
            raise ValueError(f"Duplicate host result from Loki: {host}")
        counts[host] = int(value)

    Session = get_session_factory()
    with Session.begin() as session:
        # Host inventory is independent of current Loki activity.
        hosts = session.scalars(select(Source).where(Source.source_type == "host")).all()
        known_names = {source.source_name for source in hosts}
        unknown = set(counts) - known_names
        if unknown:
            raise RuntimeError(
                "Loki has hosts absent from inventory; run activity_persistence first: "
                + ", ".join(sorted(unknown))
            )
        inserted = 0
        for source in hosts:
            statement = insert(EventVolumeObservation).values(
                source_id=source.id, window_start=start, window_end=end,
                event_count=counts.get(source.source_name, 0),
            ).on_conflict_do_nothing(
                constraint="uq_event_volume_source_window"
            ).returning(EventVolumeObservation.id)
            if session.execute(statement).scalar_one_or_none() is not None:
                inserted += 1

    return VolumeSummary(start, end, len(hosts), len(counts), inserted, sum(counts.values()))

def main() -> None:
    summary = collect_host_volume()
    print("Daystrom event-volume scan committed:")
    print(f"  Window UTC:         {summary.window_start.isoformat()} to {summary.window_end.isoformat()}")
    print(f"  Inventoried hosts:   {summary.known_hosts}")
    print(f"  Hosts with events:   {summary.hosts_with_events}")
    print(f"  Rows inserted:       {summary.observations_inserted}")
    print(f"  Total host events:   {summary.total_events}")
    print("Zero means no events in the window, not necessarily host failure.")

if __name__ == "__main__":
    main()
