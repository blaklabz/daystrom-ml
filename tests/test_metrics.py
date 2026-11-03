import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy.dialects import postgresql
from daystrom.metrics import collect, parse_vector


class TestMetrics(unittest.TestCase):
    def test_vector(self):
        self.assertEqual(parse_vector([{'metric': {'instance': 'alfred'}, 'value': [1, '42.5']}]), {'alfred': 42.5})

    def test_nonfinite_skipped(self):
        self.assertEqual(parse_vector([{'metric': {'instance': 'alfred'}, 'value': [1, 'NaN']}]), {})

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            parse_vector([
                {'metric': {'instance': 'a'}, 'value': [1, '1']},
                {'metric': {'instance': 'a'}, 'value': [1, '2']},
            ])

    def test_missing_instance_rejected(self):
        with self.assertRaises(ValueError):
            parse_vector([{'metric': {}, 'value': [1, '1']}])

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            collect(at=datetime.now(timezone.utc), backfill_windows=0)

    def _collect_with_mocked_db(self, *, at, retention_days=None, query_side_effect=None):
        client = MagicMock()
        client.query.side_effect = query_side_effect
        if query_side_effect is None:
            client.query.return_value = []

        session = MagicMock()
        session.execute.return_value.rowcount = 3
        session_factory = MagicMock()
        session_factory.begin.return_value.__enter__.return_value = session

        with patch('daystrom.metrics.get_session_factory', return_value=session_factory):
            kwargs = {'client': client, 'at': at, 'backfill_windows': 1}
            if retention_days is not None:
                kwargs['retention_days'] = retention_days
            result = collect(**kwargs)
        return result, session, client

    def test_default_retention_delete_uses_strict_180_day_cutoff(self):
        now = datetime(2026, 11, 3, 19, 30, tzinfo=timezone.utc)
        with patch.dict('os.environ', {'DAYSTROM_METRICS_RETENTION_DAYS': '180'}):
            summary, session, client = self._collect_with_mocked_db(at=now)

        self.assertEqual(summary.deleted, 3)
        self.assertEqual(client.query.call_count, 6)
        statements = [call.args[0] for call in session.execute.call_args_list]
        self.assertEqual(len(statements), 1)
        statement = statements[0]
        self.assertEqual(statement.__visit_name__, 'delete')
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        self.assertIn('DELETE FROM node_metric_observations', sql)
        self.assertIn('node_metric_observations.window_end <', sql)
        self.assertNotIn('node_metric_observations.window_end <=', sql)
        self.assertIn(now - timedelta(days=180), compiled.params.values())

    def test_explicit_retention_overrides_environment(self):
        now = datetime(2026, 11, 3, 19, 30, tzinfo=timezone.utc)
        with patch.dict('os.environ', {'DAYSTROM_METRICS_RETENTION_DAYS': '90'}):
            _, session, _ = self._collect_with_mocked_db(at=now, retention_days=180)
        statement = session.execute.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertIn(now - timedelta(days=180), compiled.params.values())
        self.assertNotIn(now - timedelta(days=90), compiled.params.values())

    def test_prometheus_failure_prevents_database_writes_and_cleanup(self):
        now = datetime(2026, 11, 3, 19, 30, tzinfo=timezone.utc)
        client = MagicMock()
        client.query.side_effect = RuntimeError('Prometheus unavailable')
        session_factory = MagicMock()
        with patch('daystrom.metrics.get_session_factory', return_value=session_factory):
            with self.assertRaisesRegex(RuntimeError, 'Prometheus unavailable'):
                collect(client=client, at=now, backfill_windows=1)
        session_factory.begin.assert_not_called()

    def test_invalid_retention_rejected_before_database_access(self):
        now = datetime(2026, 11, 3, 19, 30, tzinfo=timezone.utc)
        with patch('daystrom.metrics.get_session_factory') as factory:
            for days in (0, -1, 3651):
                with self.subTest(days=days), self.assertRaises(ValueError):
                    collect(at=now, backfill_windows=1, retention_days=days)
            factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
