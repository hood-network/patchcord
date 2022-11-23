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

import json
import zlib
import asyncio
import urllib.parse
import collections
from typing import Optional

import pytest
import websockets
from logbook import Logger
from wsproto import WSConnection, ConnectionType
from wsproto.connection import ConnectionState
from wsproto.events import (
    Request,
    Message,
    AcceptConnection,
    CloseConnection,
    Ping,
)

from litecord.gateway.opcodes import OP
from litecord.gateway.websocket import decode_etf

# Z_SYNC_FLUSH suffix
ZLIB_SUFFIX = b"\x00\x00\xff\xff"


log = Logger("test_websocket")

RcvdWrapper = collections.namedtuple("RcvdWrapper", "code reason")


class AsyncWebsocket:
    """websockets-compatible websocket object"""

    def __init__(self, url):
        self.url = url
        self.ws = WSConnection(ConnectionType.CLIENT)
        self.reader, self.writer = None, None

    async def send(self, data):
        assert self.writer is not None

        # wrap all strings in Message
        if isinstance(data, str):
            data = Message(data=data)

        log.debug("sending {} event", type(data))

        self.writer.write(self.ws.send(data))
        await self.writer.drain()

    async def recv(self, *, expect=Message, process_event: bool = True):

        # this loop is only done so we reply to pings while also being
        # able to receive any other event in the middle.
        #
        # CloseConnection does not lead us to reading other events, so
        # that's why it's left out.

        while True:
            # if there's already an unprocessed event we can try getting
            # it from wsproto first
            event = None
            for event in self.ws.events():
                break

            if event is None:
                data = await self.reader.read(4096)
                assert data  # We expect the WebSocket to be closed correctly
                self.ws.receive_data(data)
                continue

            # if we get a ping, reply with pong immediately
            # and fetch the next event
            if isinstance(event, Ping):
                await self.send(event.response())
                continue

            break

        if isinstance(event, CloseConnection):
            assert self.ws.state is ConnectionState.REMOTE_CLOSING
            await self.send(event.response())
            if process_event:
                raise websockets.ConnectionClosed(RcvdWrapper(event.code, event.reason), None)

        if expect is not None and not isinstance(event, expect):
            raise AssertionError(f"Expected {expect!r} websocket event, got {type(event)!r}")

        # this keeps compatibility with code written for aaugustin/websockets
        if expect is Message and process_event:
            return event.data

        return event

    async def close(self, close_code: int, close_reason: str):
        log.info("closing connection")
        event = CloseConnection(code=close_code, reason=close_reason)
        await self.send(event)
        self.writer.close()
        await self.writer.wait_closed()
        self.ws.receive_data(None)

    async def connect(self):
        parsed = urllib.parse.urlparse(self.url)
        if parsed.scheme == "wss":
            port = 443
        elif parsed.scheme == "ws":
            port = 80
        else:
            raise AssertionError("Invalid url scheme")

        host, *rest = parsed.netloc.split(":")
        if rest:
            port = rest[0]

        log.info("connecting to {!r} {}", host, port)
        self.reader, self.writer = await asyncio.open_connection(host, port)

        path = parsed.path or "/"
        target = f"{path}?{parsed.query}" if parsed.query else path
        await self.send(Request(host=parsed.netloc, target=target))
        await self.recv(expect=AcceptConnection)


async def _recv(conn, *, zlib_stream: bool):
    if zlib_stream:
        try:
            conn._zlib_context
        except AttributeError:
            conn._zlib_context = zlib.decompressobj()

        # inspired by
        # https://discord.com/developers/docs/topics/gateway#transport-compression-transport-compression-example
        zlib_buffer = bytearray()
        while True:
            # keep receiving frames until we find the zlib prefix inside
            # we set process_event to false so that we get the entire event
            # instead of only data
            event = await conn.recv(process_event=False)
            zlib_buffer.extend(event.data)
            if not event.message_finished:
                continue

            if len(zlib_buffer) < 4 or zlib_buffer[-4:] != ZLIB_SUFFIX:
                raise RuntimeError("Finished compressed message without ZLIB suffix")

            # NOTE: the message is utf-8 encoded.
            msg = conn._zlib_context.decompress(zlib_buffer)
            return msg
    else:
        return await conn.recv()


async def _json(conn, *, zlib_stream: bool = False):
    data = await _recv(conn, zlib_stream=zlib_stream)
    return json.loads(data)


async def _etf(conn, *, zlib_stream: bool = False):
    data = await _recv(conn, zlib_stream=zlib_stream)
    return decode_etf(data)


async def _json_send(conn, data):
    frame = json.dumps(data)
    await conn.send(frame)


async def _json_send_op(conn, opcode, data=None):
    await _json_send(conn, {"op": opcode, "d": data})


async def _close(conn):
    await conn.close(1000, "test end")


async def extract_and_verify_ready(conn, **kwargs):
    ready = await _json(conn, **kwargs)
    assert ready["op"] == OP.DISPATCH
    assert ready["t"] == "READY"

    data = ready["d"]

    # NOTE: change if default gateway changes
    assert data["v"] == 6

    # make sure other fields exist and are with
    # proper types.
    assert isinstance(data["user"], dict)
    assert isinstance(data["private_channels"], list)
    assert isinstance(data["guilds"], list)
    assert isinstance(data["session_id"], str)
    assert isinstance(data["_trace"], list)

    if "shard" in data:
        assert isinstance(data["shard"], list)


async def get_gw(test_cli, version: int) -> str:
    """Get the Gateway URL."""
    gw_resp = await test_cli.get(f"/api/v{version}/gateway")
    gw_json = await gw_resp.json
    return gw_json["url"]


async def gw_start(test_cli, *, version: int = 6, etf=False, compress: Optional[str] = None):
    """Start a websocket connection"""
    gw_url = await get_gw(test_cli, version)

    if etf:
        gw_url = f"{gw_url}?v={version}&encoding=etf"
    else:
        gw_url = f"{gw_url}?v={version}&encoding=json"

    compress = f"&compress={compress}" if compress else ""

    ws = AsyncWebsocket(f"{gw_url}{compress}")
    await ws.connect()
    return ws


@pytest.mark.asyncio
async def test_gw(test_cli):
    """Test if the gateway connects and sends a proper
    HELLO payload."""
    conn = await gw_start(test_cli)

    hello = await _json(conn)
    assert hello["op"] == OP.HELLO

    assert isinstance(hello["d"], dict)
    assert isinstance(hello["d"]["heartbeat_interval"], int)
    assert isinstance(hello["d"]["_trace"], list)

    await _close(conn)


@pytest.mark.asyncio
async def test_ready(test_cli_user):
    conn = await gw_start(test_cli_user.cli)

    # get the hello frame but ignore it
    await _json(conn)

    await _json_send(conn, {"op": OP.IDENTIFY, "d": {"token": test_cli_user.user["token"]}})

    # try to get a ready
    try:
        await _json(conn)
        assert True
    except (Exception, websockets.ConnectionClosed):
        assert False
    finally:
        await _close(conn)


@pytest.mark.asyncio
async def test_broken_identify(test_cli_user):
    conn = await gw_start(test_cli_user.cli)

    # get the hello frame but ignore it
    await _json(conn)

    await _json_send(conn, {"op": OP.IDENTIFY, "d": {"token": True}})

    # try to get a ready
    try:
        await _json(conn)
        raise AssertionError("Received a JSON message but expected close")
    except websockets.ConnectionClosed as exc:
        assert exc.code == 4002


@pytest.mark.asyncio
async def test_ready_fields(test_cli_user):
    conn = await gw_start(test_cli_user.cli)

    # get the hello frame but ignore it
    await _json(conn)

    await _json_send(conn, {"op": OP.IDENTIFY, "d": {"token": test_cli_user.user["token"]}})

    try:
        await extract_and_verify_ready(conn)

    finally:
        await _close(conn)


@pytest.mark.asyncio
async def test_ready_v9(test_cli_user):
    conn = await gw_start(test_cli_user.cli, version=9)
    await _json(conn)
    await _json_send(conn, {"op": OP.IDENTIFY, "d": {"token": test_cli_user.user["token"]}})

    try:
        ready = await _json(conn)
        assert isinstance(ready, dict)
        assert ready["op"] == OP.DISPATCH
        assert ready["t"] == "READY"

        data = ready["d"]
        assert isinstance(data, dict)
        assert data["v"] == 9
        assert isinstance(data["user"], dict)
        assert isinstance(data["relationships"], list)

        ready = await _json(conn)
        assert isinstance(ready, dict)
        assert ready["op"] == OP.DISPATCH
        assert ready["t"] == "READY_SUPPLEMENTAL"
    finally:
        await _close(conn)


@pytest.mark.asyncio
async def test_heartbeat(test_cli_user):
    conn = await gw_start(test_cli_user.cli)

    # get the hello frame but ignore it
    await _json(conn)

    await _json_send(conn, {"op": OP.IDENTIFY, "d": {"token": test_cli_user.user["token"]}})

    # ignore ready data
    ready = await _json(conn)
    assert isinstance(ready, dict)
    assert ready["op"] == OP.DISPATCH
    assert ready["t"] == "READY"

    # test a heartbeat
    await _json_send_op(conn, OP.HEARTBEAT)
    recv = await _json(conn)
    assert isinstance(recv, dict)
    assert recv["op"] == OP.HEARTBEAT_ACK

    await _close(conn)


@pytest.mark.asyncio
async def test_etf(test_cli):
    """Test if the websocket can send a HELLO message over ETF."""
    conn = await gw_start(test_cli, etf=True)

    try:
        hello = await _etf(conn)
        assert hello["op"] == OP.HELLO
    finally:
        await _close(conn)


@pytest.mark.asyncio
async def test_resume(test_cli_user):
    conn = await gw_start(test_cli_user.cli)

    # get the hello frame but ignore it
    await _json(conn)

    await _json_send(conn, {"op": OP.IDENTIFY, "d": {"token": test_cli_user.user["token"]}})

    try:
        ready = await _json(conn)
        assert isinstance(ready, dict)
        assert ready["op"] == OP.DISPATCH
        assert ready["t"] == "READY"

        data = ready["d"]
        assert isinstance(data, dict)

        assert isinstance(data["session_id"], str)
        sess_id: str = data["session_id"]
    finally:
        await _close(conn)

    # try to resume
    conn = await gw_start(test_cli_user.cli)
    _ = await _json(conn)

    await _json_send(
        conn,
        {
            "op": OP.RESUME,
            "d": {
                "token": test_cli_user.user["token"],
                "session_id": sess_id,
                "seq": 0,
            },
        },
    )

    msg = await _json(conn)
    assert isinstance(msg, dict)
    assert isinstance(msg["op"], int)
    assert msg["op"] == OP.DISPATCH
    assert isinstance(msg["t"], str)
    assert msg["t"] in ("RESUMED", "PRESENCE_REPLACE")

    # close again, and retry again, but this time by removing the state
    # and asserting the session won't be resumed.
    await _close(conn)

    conn = await gw_start(test_cli_user.cli)
    _ = await _json(conn)

    async with test_cli_user.app.app_context():
        test_cli_user.app.state_manager.remove(sess_id)

    await _json_send(
        conn,
        {
            "op": OP.RESUME,
            "d": {
                "token": test_cli_user.user["token"],
                "session_id": sess_id,
                "seq": 0,
            },
        },
    )

    msg = await _json(conn)
    assert isinstance(msg, dict)
    assert isinstance(msg["op"], int)
    assert msg["op"] == OP.INVALID_SESSION


@pytest.mark.asyncio
async def test_ready_bot(test_cli_bot):
    conn = await gw_start(test_cli_bot.cli)
    await _json(conn)  # ignore hello
    await _json_send(conn, {"op": OP.IDENTIFY, "d": {"token": test_cli_bot.user["token"]}})

    try:
        await extract_and_verify_ready(conn)
    finally:
        await _close(conn)


@pytest.mark.asyncio
async def test_ready_bot_zlib_stream(test_cli_bot):
    conn = await gw_start(test_cli_bot.cli, compress="zlib-stream")
    await _json(conn, zlib_stream=True)  # ignore hello
    await _json_send(
        conn,
        {"op": OP.IDENTIFY, "d": {"token": test_cli_bot.user["token"]}},
    )

    try:
        await extract_and_verify_ready(conn, zlib_stream=True)
    finally:
        await _close(conn)
