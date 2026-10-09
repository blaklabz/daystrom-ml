"""Persist one bounded Loki activity scan to Daystrom PostgreSQL.

Run: python -m daystrom.activity_persistence
A failed Loki query aborts the scan before any database writes.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from daystrom.db import get_session_factory
from daystrom.loki import LokiClient
from daystrom.models import ActivityObservation, Source


def _ns(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000_000)


def _key(kind: str, labels: dict[str, str]) -> str:
    canonical = json.dumps([kind, labels], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _matcher(labels: dict[str, str]) -> str:
    if not labels:
        raise ValueError("Cannot query an unlabeled stream")
    parts = []
    for key, value in sorted(labels.items()):
        # JSON quoted strings use LogQL-compatible escaping.
        parts.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
    return "{" + ",".join(parts) + "}"


@dataclass(frozen=True)
class ScanSummary:
    discovered_hosts: int
    discovered_streams: int
    sources_saved: int
    observations_saved: int
    previously_known_not_discovered: int


def persist_activity_scan(
    client: LokiClient | None = None,
    *,
    discovery_hours: float = 24,
    lookback_hours: float = 24,
) -> ScanSummary:
    """Discover sources, query latest events, then commit all results atomically.

    Existing sources absent from current discovery are preserved, with an
    explicit NOT_DISCOVERED observation. No health conclusions are drawn.
    """
    if discovery_hours <= 0 or lookback_hours <= 0:
        raise ValueError("Discovery and lookback must be positive")

    client = client or LokiClient()
    observed_at = datetime.now(timezone.utc)
    start_ns = _ns(observed_at - timedelta(hours=lookback_hours))
    end_ns = _ns(observed_at)

    # Collect everything before opening a write transaction. An API failure
    # leaves the previous inventory and observations untouched.
    streams = client.discover_streams(hours=discovery_hours)
    hosts = sorted({s["host"] for s in streams if s.get("host")})
    current: dict[tuple[str, str], tuple[str, dict[str, str], datetime | None]] = {}

    for host in hosts:
        labels = {"host": host}
        events = client.query_events(_matcher(labels), start=start_ns, end=end_ns,
                                     limit=1, direction="backward")
        current[("host", _key("host", labels))] = (
            host, labels, events[0].timestamp if events else None
        )

    # A Loki stream is identified by its *entire* label set. Rotated files
    # remain distinct at this stage; logical stream grouping comes later.
    for labels in streams:
        if not labels:
            continue
        labels = dict(labels)
        events = client.query_events(_matcher(labels), start=start_ns, end=end_ns,
                                     limit=1, direction="backward")
        name = labels.get("host") or labels.get("app") or labels.get("job") or "unattributed"
        current[("stream", _key("stream", labels))] = (
            name, labels, events[0].timestamp if events else None
        )

    Session = get_session_factory()
    with Session.begin() as session:
        known = {(s.source_type, s.source_key): s for s in session.scalars(select(Source)).all()}
        for identity, (name, labels, last_event) in current.items():
            source = known.get(identity)
            if source is None:
                source = Source(source_type=identity[0], source_key=identity[1],
                                source_name=name, labels=labels,
                                first_seen_at=observed_at, last_discovered_at=observed_at)
                session.add(source)
                session.flush()
            else:
                source.source_name = name
                source.labels = labels
                source.last_discovered_at = observed_at

            age = max(0, int((observed_at - last_event).total_seconds())) if last_event else None
            session.add(ActivityObservation(
                source_id=source.id, observed_at=observed_at,
                last_event_at=last_event, event_age_seconds=age,
                observation_status="OBSERVED" if last_event else "NO_RECENT_EVENT",
            ))

        missing = set(known) - set(current)
        for identity in missing:
            session.add(ActivityObservation(
                source_id=known[identity].id, observed_at=observed_at,
                last_event_at=None, event_age_seconds=None,
                observation_status="NOT_DISCOVERED",
            ))

    return ScanSummary(
        discovered_hosts=len(hosts), discovered_streams=len({k for k in current if k[0] == "stream"}),
        sources_saved=len(current), observations_saved=len(current) + len(missing),
        previously_known_not_discovered=len(missing),
    )


def main() -> None:
    summary = persist_activity_scan()
    print("Daystrom activity scan committed:")
    print(f"  Hosts discovered:          {summary.discovered_hosts}")
    print(f"  Streams discovered:        {summary.discovered_streams}")
    print(f"  Active inventory entries:  {summary.sources_saved}")
    print(f"  Observations written:      {summary.observations_saved}")
    print(f"  Previously known, absent:  {summary.previously_known_not_discovered}")
    print("Statuses describe Loki observations, not machine health.")


if __name__ == "__main__":
    main()
