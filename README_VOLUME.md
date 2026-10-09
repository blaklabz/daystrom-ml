# Daystrom event-volume v1

These are **drop-in files**, not a standalone clone of the whole Git repository.
Unzip at the root of your existing `daystrom-ml` checkout on **LaForge**, review `git diff`, commit/push, then pull on Daystrom.

Files:
- `daystrom/models.py` — full existing model definitions plus generic `EventVolumeObservation`
- `migrations/versions/002_event_volume.py` — manual migration (no LaForge database required)
- `daystrom/loki.py` — full client with `query_instant` added
- `daystrom/event_volume.py` — five-minute host-level collector

On Daystrom, after `git pull`:

```sh
alembic upgrade head
python -m daystrom.activity_persistence
python -m daystrom.event_volume
python -m daystrom.event_volume  # same window: 0 inserted
```

Verify:
```sql
SELECT s.source_name, v.window_start, v.window_end, v.event_count
FROM event_volume_observations v
JOIN sources s ON s.id=v.source_id
ORDER BY v.window_end DESC, v.event_count DESC
LIMIT 20;
```

Important:
- This version measures **host** sources only; the schema supports all source types.
- Loki grouped results omit zero-event hosts; existing inventoried hosts get zero.
- If Loki reports a host not in inventory, collection aborts without writes; run discovery first.
- A successful query is required before any writes.
- Measurements for hosts and future streams overlap; do not add them together as distinct events.
- An aligned window may include late-arriving logs; this version does not backfill or revise previously recorded counts. Schedule with a small delay after each five-minute boundary if needed.
- This package does **not** install a timer/cron job.
