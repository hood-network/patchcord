"""

Litecord
Copyright (C) 2018-2021  Luna Mendes and Litecord Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

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
    resp = await test_cli.get("/api/v6/gateway")
    assert resp.status_code == 200
    hdrs = resp.headers
    assert "X-RateLimit-Limit" in hdrs
    assert "X-RateLimit-Remaining" in hdrs
    assert "X-RateLimit-Reset" in hdrs
    assert "X-RateLimit-Global" in hdrs
