import json
import logging
import collections

import earl

from ..errors import WebsocketClose, AuthError
from ..auth import raw_token_check
from .errors import DecodeError, UnknownOPCode
from .opcodes import OP
from .state import GatewayState, gen_session_id


log = logging.getLogger(__name__)
WebsocketProperties = collections.namedtuple(
    'WebsocketProperties', 'v encoding compress')


def encode_json(payload) -> str:
    return json.dumps(payload)


def decode_json(data: str):
    return json.loads(data)


def encode_etf(payload) -> str:
    return earl.pack(payload)


def decode_etf(data):
    return earl.unpack(data)


class GatewayWebsocket:
    """Main gateway websocket logic."""
    def __init__(self, app, ws, **kwargs):
        self.app = app
        self.ws = ws

        self.wsp = WebsocketProperties(kwargs.get('v'),
                                       kwargs.get('encoding', 'json'),
                                       kwargs.get('compress', None))

        self.state = None

        self._set_encoders()

    def _set_encoders(self):
        encoding = self.wsp.encoding

        encodings = {
            'json': (encode_json, decode_json),
            'etf': (encode_etf, decode_etf),
        }

        self.encoder, self.decoder = encodings[encoding]

    async def send(self, payload: dict):
        """Send a payload to the websocket"""
        encoded = self.encoder(payload)

        # TODO: compression

        await self.ws.send(encoded)

    async def send_hello(self):
        """Send the OP 10 Hello packet over the websocket."""
        await self.send({
            'op': OP.HELLO,
            'd': {
                'heartbeat_interval': 45000,
                '_trace': [
                    'despacito'
                ],
            }
        })

    async def dispatch(self, event, data):
        """Dispatch an event to the websocket."""
        await self.send({
            'op': OP.DISPATCH,
            't': event.upper(),
            # 's': self.state.seq,
            'd': data,
        })

    async def handle_0(self, payload: dict):
        """Handle the OP 0 Identify packet."""
        data = payload['d']
        try:
            token, properties = data['token'], data['properties']
        except KeyError:
            raise DecodeError('Invalid identify parameters')

        compress = data.get('compress', False)
        large = data.get('large_threshold', 50)

        shard = data.get('shard', [0, 1])
        presence = data.get('presence')

        try:
            user_id = await raw_token_check(token)
        except AuthError:
            raise WebsocketClose(4004, 'Authentication failed')

        session_id = gen_session_id()

        self.state = GatewayState(
            session_id=session_id,
            user_id=user_id,
            properties=properties,
            compress=compress,
            large=large,
            shard=shard,
            presence=presence
        )

        self.app.state_manager.insert(self.state)

        # TODO: dispatch READY
        await self.dispatch('READY', {
            'v': 6,
            'user': {'i': 'Boobs !! ! .........'},
            'private_channels': [],
            'guilds': [],
            'session_id': session_id,
            '_trace': ['despacito']
        })

    async def process_message(self, payload):
        """Process a single message coming in from the client."""
        try:
            op_code = payload['op']
        except KeyError:
            raise UnknownOPCode('No OP code')

        try:
            handler = getattr(self, f'handle_{op_code}')
        except AttributeError:
            raise UnknownOPCode('Bad OP code')

        await handler(payload)

    async def listen_messages(self):
        """Listen for messages coming in from the websocket."""
        while True:
            message = await self.ws.recv()
            if len(message) > 4096:
                raise DecodeError('Payload length exceeded')

            payload = self.decoder(message)
            await self.process_message(payload)

    async def run(self):
        """Wrap listen_messages inside
        a try/except block for WebsocketClose handling."""
        try:
            await self.send_hello()
            await self.listen_messages()
        except WebsocketClose as err:
            log.warning(f'Closed a client, {self.state or "<none>"} {err!r}')
            await self.ws.close(code=err.code,
                                reason=err.reason)
