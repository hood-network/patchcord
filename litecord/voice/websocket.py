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
from dataclasses import dataclass, asdict, field

import websockets.errors
from logbook import Logger

from litecord.voice.opcodes import VoiceOP

from litecord.errors import WebsocketClose
from litecord.voice.errors import (
    UnknownOPCode, AuthFailed, UnknownProtocol, InvalidSession
)

from litecord.enums import ChannelType, VOICE_CHANNELS

log = Logger(__name__)


@dataclass
class VoiceState:
    """Store a voice websocket's state."""
    server_id: int
    user_id: int

    def __bool__(self):
        as_dict = asdict(self)
        return all(bool(v) for v in as_dict.values())


class VoiceWebsocket:
    """Voice websocket class.

    Implements the Discord Voice Websocket Protocol Version 4.
    """
    def __init__(self, ws, app):
        self.ws = ws
        self.app = app
        self.voice = app.voice
        self.storage = app.storage

        self.state = None

    async def send_op(self, opcode: VoiceOP, data: dict):
        """Send a message through the websocket."""
        encoded = json.dumps({
            'op': opcode,
            'd': data
        })

        await self.ws.send(encoded)

    async def _handle_0(self, msg: dict):
        """Handle OP 0 Identify."""
        data = msg['d']

        # NOTE: there is a data.video, but we don't handle video.
        try:
            server_id = int(data['server_id'])
            user_id = int(data['user_id'])
            session_id = data['session_id']
            token = data['token']
        except (KeyError, ValueError):
            raise AuthFailed('Invalid identify payload')

        # server_id can be a:
        #  - voice channel id
        #  - dm id
        #  - group dm id

        channel = await self.storage.get_channel(server_id)
        ctype = ChannelType(channel['type'])

        if ctype not in VOICE_CHANNELS:
            raise AuthFailed('invalid channel id')

        v_user_id = await self.voice.authenticate(token, session_id)

        if v_user_id != user_id:
            raise AuthFailed('invalid user id')

        await self.send_op(VoiceOP.hello, {
            'v': 4,
            'heartbeat_interval': 10000,
        })

        # TODO: get ourselves a place on the voice server
        place = await self.voice.get_place(server_id)

        if not place:
            raise InvalidSession('invalid voice place')

        self.state = VoiceState(place.server_id, user_id)

        await self.send_op(VoiceOP.ready, {
            'ssrc': place.ssrc,
            'port': place.port,
            'modes': place.modes,
            'ip': place.ip,
        })

    async def _handle_1(self, msg: dict):
        """Handle 1 Select Protocol."""
        data = msg['d']

        try:
            protocol = data['protocol']
            proto_data = data['data']
        except KeyError:
            raise UnknownProtocol('invalid select protocol')

        if protocol != 'udp':
            raise UnknownProtocol('invalid protocol')

        try:
            client_addr = proto_data['address']
            client_port = proto_data['port']
            client_mode = proto_data['mode']
        except KeyError:
            raise UnknownProtocol('incomplete protocol data')

        # signal the voice server about (address, port) + mode
        session = await self.voice.register(
            self.state.server_id,
            client_addr, client_port, client_mode
        )

        await self.send_op(VoiceOP.session_description, {
            'video_codec': 'VP8',
            'secret_key': session.key,
            'mode': session.mode,
            'media_session_id': session.sess_id,
            'audio_codec': 'opus'
        })

    async def _handle_3(self, msg: dict):
        """Handle 3 Heartbeat."""
        await self.send_op(VoiceOP.heartbeat_ack, {
            'd': msg['d']
        })

    async def _handle_5(self, msg: dict):
        """Handle 5 Speaking."""
        if not self.state:
            return

        await self.voice.update(self.state, msg['d'])
    
    async def _handle_7(self, msg: dict):
        """Handle 7 Resume."""
        pass

    async def _process_msg(self):
        msg = await self.ws.recv()
        msg = json.loads(msg)
        op_code = msg['op']

        try:
            handler = getattr(self, f'_handle_{op_code}')
        except AttributeError:
            raise UnknownOPCode('Unknown OP code.')

        await handler(msg)

    async def _loop(self):
        while True:
            await self._process_msg()

    async def run(self):
        """Main entry point for a voice websocket."""
        try:
            await self._loop()
        except websockets.exceptions.ConnectionClosed as err:
            log.warning('conn close, state={}, err={}', self.state, err)
        except WebsocketClose as err:
            log.warning('ws close, state={} err={}', self.state, err)
            await self.ws.close(code=err.code, reason=err.reason)
        except Exception as err:
            log.exception('An exception has occoured. state={}', self.state)
            await self.ws.close(code=4000, reason=repr(err))
