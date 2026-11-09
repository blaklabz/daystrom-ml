"""Authenticated, read-only API for curated Daystrom node observations."""
import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from sqlalchemy import func, select

from daystrom.db import get_session_factory
from daystrom.models import NodeMetricObservation

METRICS = frozenset({
    'cpu_used_pct', 'memory_used_pct', 'memory_available_bytes',
    'disk_used_pct_max', 'network_receive_bytes_per_second',
    'network_transmit_bytes_per_second',
})
MAX_INSTANCES = 100
FRESH_SECONDS = 900
app = FastAPI(title='Daystrom Read-Only API', docs_url=None, redoc_url=None, openapi_url=None)


def require_token(authorization: str | None = Header(default=None)) -> None:
    token = os.getenv('DAYSTROM_API_TOKEN')
    if not token:
        raise HTTPException(status_code=503, detail='API authentication not configured')
    supplied = authorization.removeprefix('Bearer ') if authorization and authorization.startswith('Bearer ') else ''
    if not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail='Unauthorized')


@app.get('/v1/instances', dependencies=[Depends(require_token)])
def list_instances(limit: int = Query(default=50, ge=1, le=MAX_INSTANCES)) -> dict:
    """Return latest known observation for each curated metric on each listed instance.

    The limit applies to distinct instances; more_available is true when truncated.
    Historical observations are not evidence that a machine is currently running.
    """
    now = datetime.now(timezone.utc)
    Session = get_session_factory()
    with Session() as session:
        # Select one additional instance to reliably signal truncation.
        names = session.scalars(
            select(NodeMetricObservation.instance)
            .where(NodeMetricObservation.metric_name.in_(METRICS))
            .distinct()
            .order_by(NodeMetricObservation.instance)
            .limit(limit + 1)
        ).all()
        more_available = len(names) > limit
        names = names[:limit]
        rows = []
        if names:
            latest = (
                select(
                    NodeMetricObservation.instance,
                    NodeMetricObservation.metric_name,
                    func.max(NodeMetricObservation.window_end).label('latest_window'),
                )
                .where(NodeMetricObservation.instance.in_(names), NodeMetricObservation.metric_name.in_(METRICS))
                .group_by(NodeMetricObservation.instance, NodeMetricObservation.metric_name)
                .subquery()
            )
            rows = session.scalars(
                select(NodeMetricObservation)
                .join(latest, (
                    (NodeMetricObservation.instance == latest.c.instance)
                    & (NodeMetricObservation.metric_name == latest.c.metric_name)
                    & (NodeMetricObservation.window_end == latest.c.latest_window)
                ))
                .order_by(NodeMetricObservation.instance, NodeMetricObservation.metric_name)
            ).all()
        instances = {name: {'instance': name, 'metrics': {}} for name in names}
        for row in rows:
            age = max(0, int((now - row.window_end).total_seconds()))
            instances[row.instance]['metrics'][row.metric_name] = {
                'value': row.value,
                'window_end': row.window_end.isoformat(),
                'collected_at': row.collected_at.isoformat(),
                'age_seconds': age,
                'fresh': age <= FRESH_SECONDS,
            }
    return {
        'ok': True,
        'generated_at': now.isoformat(),
        'freshness_threshold_seconds': FRESH_SECONDS,
        'limit': limit,
        'more_available': more_available,
        'instance_count': len(instances),
        'instances': list(instances.values()),
        'note': 'Freshness describes observation age, not host health. Missing data is not zero or proof of outage.',
    }
