import sys
import os
sys.path.append(os.getcwd())

import pytest

from tests.common import login


@pytest.mark.asyncio
async def test_gw(test_cli):
    """Test if the gateway route is sane."""
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
