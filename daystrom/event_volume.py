"""Persist aligned Loki host event counts, including bounded missing-window backfill.

Run: python -m daystrom.event_volume

Measurements reference generic Source IDs; only the current collection adapter
uses the Loki 'host' label. Other source types can reuse the measurement table.
"""
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from daystrom.db import get_session_factory
from daystrom.loki import LokiClient
from daystrom.models import EventVolumeObservation, Source

WINDOW_SECONDS = 300
DEFAULT_BACKFILL_WINDOWS = 12


@dataclass(frozen=True)
class VolumeSummary:
    windows_checked: int
    observations_inserted: int
    total_events: int
    latest_window_start: datetime
    latest_window_end: datetime


def _counts_for_window(client: LokiClient, end: datetime) -> dict[str, int]:
    expression = 'sum by (host) (count_over_time({host=~".+"}[5m]))'
    payload = client.query_instant(expression, at=end)
    counts: dict[str, int] = {}
    for row in payload['data']['result']:
        host = row.get('metric', {}).get('host')
        if not host:
            raise ValueError('Loki returned a result without a host label')
        value = float(row['value'][1])
        if not value.is_integer() or value < 0:
            raise ValueError(f'Invalid Loki event count for {host}: {value}')
        if host in counts:
            raise ValueError(f'Duplicate host result from Loki: {host}')
        counts[host] = int(value)
    return counts


def collect_host_volume(
    client: LokiClient | None = None,
    *,
    at: datetime | None = None,
    max_backfill_windows: int | None = None,
    ingestion_delay_seconds: int = 30,
) -> VolumeSummary:
    """Fill missing measurements in a bounded set of completed five-minute windows.

    Each window is committed atomically. Loki failures never produce zero counts.
    Existing measurements are immutable. Sources first discovered after the
    start of a window are not assigned retroactive zero measurements.

    NOTE: A successful Loki query cannot prove historical data completeness;
    keep backfill within Loki retention and allow ingestion delay.
    """
    client = client or LokiClient()
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('at must be timezone-aware')
    if ingestion_delay_seconds < 0:
        raise ValueError('ingestion_delay_seconds must be nonnegative')
    if max_backfill_windows is None:
        max_backfill_windows = int(os.getenv('DAYSTROM_BACKFILL_WINDOWS', DEFAULT_BACKFILL_WINDOWS))
    if max_backfill_windows < 1 or max_backfill_windows > 288:
        raise ValueError('max_backfill_windows must be between 1 and 288')

    cutoff = now.astimezone(timezone.utc) - timedelta(seconds=ingestion_delay_seconds)
    latest_end_epoch = int(cutoff.timestamp()) // WINDOW_SECONDS * WINDOW_SECONDS
    latest_end = datetime.fromtimestamp(latest_end_epoch, tz=timezone.utc)
    first_end = latest_end - timedelta(seconds=WINDOW_SECONDS * (max_backfill_windows - 1))
    Session = get_session_factory()
    windows_checked = inserted = total_events = 0

    for index in range(max_backfill_windows):
        end = first_end + timedelta(seconds=WINDOW_SECONDS * index)
        start = end - timedelta(seconds=WINDOW_SECONDS)
        with Session() as session:
            hosts = session.scalars(select(Source).where(Source.source_type == 'host')).all()
            eligible = [s for s in hosts if s.first_seen_at <= start]
            existing_ids = set(session.scalars(select(EventVolumeObservation.source_id).where(
                EventVolumeObservation.window_start == start,
                EventVolumeObservation.window_end == end,
            )).all())
            missing = [s for s in eligible if s.id not in existing_ids]
        if not missing:
            continue

        # Query before opening a write transaction; a Loki error leaves this
        # window untouched. Don't interpret failed queries as zero events.
        counts = _counts_for_window(client, end)
        known_names = {s.source_name for s in hosts}
        unknown = set(counts) - known_names
        if unknown:
            raise RuntimeError('Loki has hosts absent from inventory; run activity_persistence first: '
                               + ', '.join(sorted(unknown)))
        with Session.begin() as session:
            for source in missing:
                statement = insert(EventVolumeObservation).values(
                    source_id=source.id,
                    window_start=start,
                    window_end=end,
                    event_count=counts.get(source.source_name, 0),
                ).on_conflict_do_nothing(
                    constraint='uq_event_volume_source_window'
                ).returning(EventVolumeObservation.id)
                if session.execute(statement).scalar_one_or_none() is not None:
                    inserted += 1
        windows_checked += 1
        total_events += sum(counts.values())

    return VolumeSummary(windows_checked, inserted, total_events,
                         latest_end - timedelta(seconds=WINDOW_SECONDS), latest_end)


def main() -> None:
    summary = collect_host_volume()
    print('Daystrom event-volume backfill committed:')
    print(f'  Latest window UTC:  {summary.latest_window_start.isoformat()} to {summary.latest_window_end.isoformat()}')
    print(f'  Windows queried:    {summary.windows_checked}')
    print(f'  Rows inserted:      {summary.observations_inserted}')
    print(f'  Queried event sum:  {summary.total_events}')
    print('Zero means no Loki events in a queried window, not host failure.')


if __name__ == '__main__':
    main()
