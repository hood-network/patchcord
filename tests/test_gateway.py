"""

Litecord
Copyright (C) 2018-2019  Luna Mendes

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

from tests.common import login


@pytest.mark.asyncio
async def test_gw(test_cli):
    """Test if the gateway route works."""
    resp = await test_cli.get('/api/v6/gateway')
    assert resp.status_code == 200
    rjson = await resp.json
    assert isinstance(rjson, dict)
    assert 'url' in rjson
    assert isinstance(rjson['url'], str)


@pytest.mark.asyncio
async def test_gw_bot(test_cli):
    """Test the Get Bot Gateway route"""
    token = await login('normal', test_cli)

    resp = await test_cli.get('/api/v6/gateway/bot', headers={
        'Authorization': token
    })

    assert resp.status_code == 200
    rjson = await resp.json

    assert isinstance(rjson, dict)
    assert isinstance(rjson['url'], str)
    assert isinstance(rjson['shards'], int)
    assert 'session_start_limit' in rjson

    ssl = rjson['session_start_limit']
    assert isinstance(ssl['total'], int)
    assert isinstance(ssl['remaining'], int)
    assert isinstance(ssl['reset_after'], int)
