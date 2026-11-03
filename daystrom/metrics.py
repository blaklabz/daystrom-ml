"""Curated node metrics, five-minute backfill and bounded retention.

Run once manually first: python -m daystrom.metrics
Missing series remain absent (never synthetic zero); late data can be recovered
by re-running within the configured backfill horizon.
"""
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from daystrom.db import get_session_factory
from daystrom.models import NodeMetricObservation
from daystrom.prometheus import PrometheusClient

WINDOW_SECONDS = 300
# Host-level derived signals; avoid duplicating raw Prometheus series.
QUERIES = {
    'cpu_used_pct': '100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{job="alloy_node",mode="idle"}[5m])))',
    'memory_used_pct': '100 * (1 - node_memory_MemAvailable_bytes{job="alloy_node"} / node_memory_MemTotal_bytes{job="alloy_node"})',
    'memory_available_bytes': 'node_memory_MemAvailable_bytes{job="alloy_node"}',
    'disk_used_pct_max': 'max by (instance) (100 * (1 - node_filesystem_avail_bytes{job="alloy_node",fstype!~"tmpfs|devtmpfs|overlay|squashfs|ramfs|nsfs|autofs|fuse.*"} / node_filesystem_size_bytes{job="alloy_node",fstype!~"tmpfs|devtmpfs|overlay|squashfs|ramfs|nsfs|autofs|fuse.*"}))',
    'network_receive_bytes_per_second': 'sum by (instance) (rate(node_network_receive_bytes_total{job="alloy_node",device!~"lo|veth.*|docker.*|br-.*|virbr.*"}[5m]))',
    'network_transmit_bytes_per_second': 'sum by (instance) (rate(node_network_transmit_bytes_total{job="alloy_node",device!~"lo|veth.*|docker.*|br-.*|virbr.*"}[5m]))',
}

@dataclass(frozen=True)
class Summary:
    windows: int
    inserted: int
    deleted: int
    latest_window_end: datetime


def parse_vector(rows):
    result = {}
    for row in rows:
        instance = row.get('metric', {}).get('instance')
        if not instance:
            raise ValueError('Prometheus returned metric without instance')
        value = float(row['value'][1])
        if not math.isfinite(value):
            continue
        if instance in result:
            raise ValueError(f'Duplicate instance in aggregated metric: {instance}')
        result[instance] = value
    return result


def collect(client=None, *, at=None, backfill_windows=None, retention_days=None, ingestion_delay_seconds=60):
    client = client or PrometheusClient()
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('at must have timezone')
    backfill_windows = int(backfill_windows if backfill_windows is not None else os.getenv('DAYSTROM_METRICS_BACKFILL_WINDOWS', '12'))
    retention_days = int(retention_days if retention_days is not None else os.getenv('DAYSTROM_METRICS_RETENTION_DAYS', '180'))
    if not 1 <= backfill_windows <= 288 or not 1 <= retention_days <= 3650 or ingestion_delay_seconds < 0:
        raise ValueError('Invalid backfill, retention or ingestion delay')
    end_epoch = int((now - timedelta(seconds=ingestion_delay_seconds)).timestamp()) // WINDOW_SECONDS * WINDOW_SECONDS
    latest = datetime.fromtimestamp(end_epoch, tz=timezone.utc)
    Session = get_session_factory()
    inserted = 0
    for offset in range(backfill_windows - 1, -1, -1):
        end = latest - timedelta(seconds=offset * WINDOW_SECONDS)
        # Fetch all queries before writing a window; failed API calls cannot
        # leave a partially collected window. Re-query to fill late arrivals.
        measurements = {name: parse_vector(client.query(expr, end)) for name, expr in QUERIES.items()}
        with Session.begin() as session:
            for name, values in measurements.items():
                for instance, value in values.items():
                    stmt = insert(NodeMetricObservation).values(
                        instance=instance, metric_name=name, window_end=end, value=value,
                    ).on_conflict_do_nothing(constraint='uq_node_metric_instance_name_end').returning(NodeMetricObservation.id)
                    if session.execute(stmt).scalar_one_or_none() is not None:
                        inserted += 1
    # Delete only after successful collection. Strictly older than cutoff.
    cutoff = now - timedelta(days=retention_days)
    with Session.begin() as session:
        deleted = session.execute(delete(NodeMetricObservation).where(NodeMetricObservation.window_end < cutoff)).rowcount
    return Summary(backfill_windows, inserted, deleted, latest)


def main():
    summary = collect()
    print(f'Daystrom metrics: windows={summary.windows} inserted={summary.inserted} '
          f'retention_deleted={summary.deleted} latest_utc={summary.latest_window_end.isoformat()}')

if __name__ == '__main__':
    main()
