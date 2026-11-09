"""API contract tests with a fake SQLAlchemy session (no production database)."""
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from daystrom.api import app


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_unconfigured_token_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get('/v1/instances')
        self.assertEqual(response.status_code, 503)

    def test_missing_or_bad_token_rejected(self):
        with patch.dict(os.environ, {'DAYSTROM_API_TOKEN': 'test-secret'}):
            self.assertEqual(self.client.get('/v1/instances').status_code, 401)
            self.assertEqual(self.client.get('/v1/instances', headers={'Authorization': 'Bearer bad'}).status_code, 401)

    def test_invalid_limit_rejected(self):
        with patch.dict(os.environ, {'DAYSTROM_API_TOKEN': 'test-secret'}):
            response = self.client.get('/v1/instances?limit=101', headers={'Authorization': 'Bearer test-secret'})
        self.assertEqual(response.status_code, 422)


if __name__ == '__main__':
    unittest.main()
