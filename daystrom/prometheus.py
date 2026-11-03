"""Read-only Prometheus instant-query client."""
import os
import httpx

class PrometheusClient:
    def __init__(self, base_url=None, timeout=30.0):
        self.base_url = (base_url or os.getenv('DAYSTROM_PROMETHEUS_URL') or 'http://prometheus.blaklabz.io:9090').rstrip('/')
        self.timeout = timeout

    def query(self, expression, at):
        response = httpx.get(f'{self.base_url}/api/v1/query',
                             params={'query': expression, 'time': str(at.timestamp())}, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get('status') != 'success' or payload.get('data', {}).get('resultType') != 'vector':
            raise RuntimeError(f'Prometheus query failed: {payload}')
        return payload['data']['result']
