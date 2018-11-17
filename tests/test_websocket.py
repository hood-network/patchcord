import pytest
import websockets
import json

from tests.common import login
from litecord.gateway.opcodes import OP


async def _json(conn):
    frame = await conn.recv()
    return json.loads(frame)


async def _json_send(conn, data):
    frame = json.dumps(data)
    await conn.send(frame)


async def get_gw(test_cli) -> str:
    """Get the Gateway URL."""
    gw_resp = await test_cli.get('/api/v6/gateway')
    gw_json = await gw_resp.json
    return gw_json['url']


async def gw_start(test_cli):
    """Start a websocket connection"""
    gw_url = await get_gw(test_cli)
    return await websockets.connect(gw_url)


@pytest.mark.asyncio
async def test_gw(test_cli):
    """Test if the gateway connects and sends a proper
    HELLO payload."""
    conn = await gw_start(test_cli)

    hello = await _json(conn)
    assert hello['op'] == OP.HELLO

    assert isinstance(hello['d'], dict)
    assert isinstance(hello['d']['heartbeat_interval'], int)
    assert isinstance(hello['d']['_trace'], list)

    await conn.close(1000, 'test end')


@pytest.mark.asyncio
async def test_ready(test_cli):
    token = await login('normal', test_cli)
    conn = await gw_start(test_cli)

    # get the hello frame but ignore it
    await _json(conn)

    await _json_send(conn, {
        'op': OP.IDENTIFY,
        'd': {
            'token': token,
        }
    })

    # try to get a ready
    try:
        await _json(conn)
        assert True
        await conn.close(1000, 'test end')
    except (Exception, websockets.ConnectionClosed):
        assert False
