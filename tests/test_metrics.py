import math
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from daystrom.metrics import parse_vector, collect

class TestMetrics(unittest.TestCase):
    def test_vector(self):
        self.assertEqual(parse_vector([{'metric': {'instance': 'alfred'}, 'value': [1, '42.5']}]), {'alfred': 42.5})
    def test_nonfinite_skipped(self):
        self.assertEqual(parse_vector([{'metric': {'instance': 'alfred'}, 'value': [1, 'NaN']}]), {})
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            parse_vector([{'metric': {'instance': 'a'}, 'value': [1, '1']}, {'metric': {'instance': 'a'}, 'value': [1, '2']}])
    def test_missing_instance_rejected(self):
        with self.assertRaises(ValueError):
            parse_vector([{'metric': {}, 'value': [1, '1']}])
    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            collect(at=datetime.now(timezone.utc), backfill_windows=0)

if __name__ == '__main__':
    unittest.main()
