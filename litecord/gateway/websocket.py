import json

import earl

from ..errors import WebsocketClose
from .errors import DecodeError, UnknownOPCode
from .opcodes import OP


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
    def __init__(self, ws, **kwargs):
        self.ws = ws
        self.version = kwargs.get('v', 6)
        self.encoding = kwargs.get('encoding', 'json')
        self.compress = kwargs.get('compress', None)

        self.set_encoders()

    def set_encoders(self):
        encoding = self.encoding

        encodings = {
            'json': (encode_json, decode_json),
            'etf': (encode_etf, decode_etf),
        }

        self.encoder, self.decoder = encodings[encoding]

    async def send(self, payload):
        encoded = self.encoder(payload)

        # TODO: compression

        await self.ws.send(encoded)

    async def send_hello(self):
        """Send the OP 10 Hello"""
        await self.send({
            'op': OP.HELLO,
            'd': {
                'heartbeat_interval': 45000,
                '_trace': [
                    'despacito'
                ],
            }
        })

    async def handle_0(self, payload):
        pass

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
            await self.ws.close(code=err.code,
                                reason=err.reason)
