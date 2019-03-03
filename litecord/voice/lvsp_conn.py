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

import json
import asyncio

import websockets
from logbook import Logger

from litecord.voice.lvsp_opcodes import OPCodes as OP

log = Logger(__name__)


class LVSPConnection:
    """Represents a single LVSP connection."""
    def __init__(self, lvsp, region: str, hostname: str):
        self.lvsp = lvsp
        self.app = lvsp.app

        self.region = region
        self.hostname = hostname

        self.conn = None

        self._hb_task = None
        self._hb_interval = None

    @property
    def _log_id(self):
        return f'region={self.region} hostname={self.hostname}'

    async def send(self, payload):
        """Send a payload down the websocket."""
        msg = json.dumps(payload)
        await self.conn.send(msg)

    async def recv(self):
        """Receive a payload."""
        msg = await self.conn.recv()
        msg = json.dumps(msg)
        return msg

    async def send_op(self, opcode: int, data: dict):
        """Send a message with an OP code included"""
        await self.send({
            'op': opcode,
            'd': data
        })

    async def _heartbeater(self, hb_interval: int):
        try:
            await asyncio.sleep(hb_interval)

            # TODO: add self._seq
            await self.send_op(OP.heartbeat, {
                's': 0
            })

            # give the server 300 milliseconds to reply.
            await asyncio.sleep(300)
            await self.conn.close(4000, 'heartbeat timeout')
        except asyncio.CancelledError:
            pass

    def _start_hb(self):
        self._hb_task = self.app.loop.create_task(
            self._heartbeater(self._hb_interval)
        )

    def _stop_hb(self):
        self._hb_task.cancel()

    async def _handle_0(self, msg):
        """Handle HELLO message."""
        data = msg['d']

        # nonce = data['nonce']
        self._hb_interval = data['heartbeat_interval']

        # TODO: send identify

    async def _update_health(self, new_health: float):
        """Update the health value of a given voice server."""
        await self.app.db.execute("""
        UPDATE voice_servers
        SET health = $1
        WHERE hostname = $2
        """, new_health, self.hostname)

    async def _handle_3(self, msg):
        """Handle READY message.

        We only start heartbeating after READY.
        """
        await self._update_health(msg['health'])
        self._start_hb()

    async def _handle_5(self, msg):
        """Handle HEARTBEAT_ACK."""
        self._stop_hb()
        await self._update_health(msg['health'])
        self._start_hb()

    async def _loop(self):
        while True:
            msg = await self.recv()

            try:
                opcode = msg['op']
                handler = getattr(self, f'_handle_{opcode}')
                await handler(msg)
            except (KeyError, AttributeError):
                # TODO: error codes in LVSP
                raise Exception('invalid op code')

    async def run(self):
        """Start the websocket."""
        self.conn = await websockets.connect(f'wss://{self.hostname}')

        try:
            await self._loop()
        except websockets.exceptions.ConnectionClosed as err:
            log.warning('conn close, {}, err={}', self._log_id, err)
        # except WebsocketClose as err:
        #     log.warning('ws close, state={} err={}', self.state, err)
        #     await self.conn.close(code=err.code, reason=err.reason)
        except Exception as err:
            log.exception('An exception has occoured. {}', self._log_id)
            await self.conn.close(code=4000, reason=repr(err))
