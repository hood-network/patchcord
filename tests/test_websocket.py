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


async def _json_send_op(conn, opcode, data=None):
    await _json_send(conn, {
        'op': opcode,
        'd': data
    })


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


@pytest.mark.asyncio
async def test_ready_fields(test_cli):
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

    ready = await _json(conn)
    assert isinstance(ready, dict)
    assert ready['op'] == OP.DISPATCH
    assert ready['t'] == 'READY'

    data = ready['d']
    assert isinstance(data, dict)

    # NOTE: change if default gateway changes
    assert data['v'] == 6

    # make sure other fields exist and are with
    # proper types.
    assert isinstance(data['user'], dict)
    assert isinstance(data['private_channels'], list)
    assert isinstance(data['guilds'], list)
    assert isinstance(data['session_id'], str)

    await conn.close(1000, 'test end')


@pytest.mark.asyncio
async def test_heartbeat(test_cli):
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

    # ignore ready data
    ready = await _json(conn)
    assert isinstance(ready, dict)
    assert ready['op'] == OP.DISPATCH
    assert ready['t'] == 'READY'

    # test a heartbeat
    await _json_send_op(conn, OP.HEARTBEAT)
    recv = await _json(conn)
    assert isinstance(recv, dict)
    assert recv['op'] == OP.HEARTBEAT_ACK
