import sys
import os
sys.path.append(os.getcwd())

import pytest

from litecord.ratelimits.bucket import Ratelimit


def test_ratelimit():
    """Test basic ratelimiting"""
    r = Ratelimit(0, 10)
    bucket = r.get_bucket(0)
    retry_after = bucket.update_rate_limit()
    assert isinstance(retry_after, float)
    assert retry_after <= 10


@pytest.mark.asyncio
async def test_ratelimit_headers(test_cli):
    """Test if the basic ratelimit headers are sent."""
    resp = await test_cli.get('/api/v6/gateway')
    assert resp.status_code == 200
    hdrs = resp.headers
    assert 'X-RateLimit-Limit' in hdrs
    assert 'X-RateLimit-Remaining' in hdrs
    assert 'X-RateLimit-Reset' in hdrs
    assert 'X-RateLimit-Global' in hdrs
