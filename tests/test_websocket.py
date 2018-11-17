import pytest
import websockets
import json

from tests.common import login
from litecord.gateway.opcodes import OP


async def _json(conn):
    frame = await conn.recv()
    return json.loads(frame)


async def get_gw(test_cli) -> str:
    """Get the Gateway URL."""
    gw_resp = await test_cli.get('/api/v6/gateway')
    gw_json = await gw_resp.json
    return gw_json['url']


async def gw_start(test_cli):
    gw_url = await get_gw(test_cli)
    return websockets.connect(gw_url)


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
