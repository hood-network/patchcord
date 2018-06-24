import json
import collections
import pprint
import zlib
from typing import List, Dict, Any

import earl
import websockets
from logbook import Logger

from litecord.errors import WebsocketClose, Unauthorized, Forbidden
from litecord.auth import raw_token_check
from .errors import DecodeError, UnknownOPCode, \
    InvalidShard, ShardingRequired
from .opcodes import OP
from .state import GatewayState


log = Logger(__name__)
WebsocketProperties = collections.namedtuple(
    'WebsocketProperties', 'v encoding compress zctx'
)

WebsocketObjects = collections.namedtuple(
    'WebsocketObjects', 'db state_manager storage loop'
)


def encode_json(payload) -> str:
    return json.dumps(payload)


def decode_json(data: str):
    return json.loads(data)


def encode_etf(payload) -> str:
    return earl.pack(payload)


def decode_etf(data: bytes):
    return earl.unpack(data)


class GatewayWebsocket:
    """Main gateway websocket logic."""

    def __init__(self, ws, **kwargs):
        self.ext = WebsocketObjects(*kwargs['prop'])
        self.storage = self.ext.storage
        self.ws = ws

        self.wsp = WebsocketProperties(kwargs.get('v'),
                                       kwargs.get('encoding', 'json'),
                                       kwargs.get('compress', None),
                                       zlib.compressobj())

        self.state = None

        self._set_encoders()

    def _set_encoders(self):
        encoding = self.wsp.encoding

        encodings = {
            'json': (encode_json, decode_json),
            'etf': (encode_etf, decode_etf),
        }

        self.encoder, self.decoder = encodings[encoding]

    async def send(self, payload: Dict[str, Any]):
        """Send a payload to the websocket.

        This function accounts for the zlib-stream
        transport method used by Discord.
        """
        log.debug('Sending {}', pprint.pformat(payload))
        encoded = self.encoder(payload)

        if not isinstance(encoded, bytes):
            encoded = encoded.encode()

        print(self.wsp.compress)
        if self.wsp.compress == 'zlib-stream':
            data1 = self.wsp.zctx.compress(encoded)
            data2 = self.wsp.zctx.flush(zlib.Z_FULL_FLUSH)

            await self.ws.send(data1 + data2)
        else:
            # TODO: pure zlib
            await self.ws.send(encoded.decode())

    async def send_hello(self):
        """Send the OP 10 Hello packet over the websocket."""
        await self.send({
            'op': OP.HELLO,
            'd': {
                'heartbeat_interval': 45000,
                '_trace': [
                    'lesbian-server'
                ],
            }
        })

    async def dispatch(self, event: str, data: Any):
        """Dispatch an event to the websocket."""
        self.state.seq += 1

        payload = {
            'op': OP.DISPATCH,
            't': event.upper(),
            's': self.state.seq,
            'd': data,
        }

        self.state.store[self.state.seq] = payload
        await self.send(payload)

    async def _make_guild_list(self) -> List[int]:
        # TODO: This function does not account for sharding.
        user_id = self.state.user_id

        guild_ids = await self.storage.get_user_guilds(user_id)

        if self.state.bot:
            return [{
                'id': row[0],
                'unavailable': True,
            } for row in guild_ids]

        return [
            {
                **await self.storage.get_guild(row[0], user_id),
                **await self.storage.get_guild_extra(row[0], user_id,
                                                     self.state.large)
            }
            for row in guild_ids
        ]

    async def guild_dispatch(self, unavailable_guilds: List[Dict[str, Any]]):
        """Dispatch GUILD_CREATE information."""

        # Users don't get asynchronous guild dispatching.
        if not self.state.bot:
            return

        for guild_obj in unavailable_guilds:
            guild = await self.storage.get_guild(guild_obj['id'],
                                                 self.state.user_id)

            if not guild:
                continue

            await self.dispatch('GUILD_CREATE', dict(guild))

    async def user_ready(self):
        """Fetch information about users in the READY packet.

        This part of the API is completly undocumented.
        PLEAS DISCORD DO NOT BAN ME
        """

        return {
            'relationships': [],
            'user_guild_settings': [],
            'notes': {},
            'friend_suggestion_count': 0,
            'presences': [],
            'read_state': [],
            'experiments': [],
            'guild_experiments': [],
            'connected_accounts': [],
            'user_settings': {
                'afk_timeout': 300,
                'animate_emoji': True,
                'convert_emoticons': False,
                'default_guilds_restricted': True,
                'detect_platform_accounts': False,
                'developer_mode': True,
                'enable_tts_command': False,
                'explicit_content_filter': 2,
                'friend_source_flags': {
                    'mutual_friends': True
                },
                'gif_auto_play': True,
                'guild_positions': [],
                'inline_attachment_media': True,
                'inline_embed_media': True,
                'locale': 'en-US',
                'message_display_compact': False,
                'render_embeds': True,
                'render_reactions': True,
                'restricted_guilds': [],
                'show_current_game': True,
                'status': 'online',
                'theme': 'dark',
                'timezone_offset': 420,
            },
            'analytics_token': 'transbian',
            'required_action': 'be gay',
        }

    async def dispatch_ready(self):
        """Dispatch the READY packet for a connecting account."""
        guilds = await self._make_guild_list()
        user = await self.storage.get_user(self.state.user_id, True)

        uready = {}
        if not self.state.bot:
            # user, fetch info
            uready = await self.user_ready()

        await self.dispatch('READY', {**{
            'v': 6,
            'user': user,
            'private_channels': [],
            'guilds': guilds,
            'session_id': self.state.session_id,
            '_trace': ['transbian']
        }, **uready})

        # async dispatch of guilds
        self.ext.loop.create_task(self.guild_dispatch(guilds))

    async def _check_shards(self):
        shard = self.state.shard
        current_shard, shard_count = shard

        guilds = await self.ext.db.fetchval("""
        SELECT COUNT(*)
        FROM members
        WHERE user_id = $1
        """, self.state.user_id)

        recommended = max(int(guilds / 1200), 1)

        if shard_count < recommended:
            raise ShardingRequired('Too many guilds for shard '
                                   f'{current_shard}')

        if guilds > 2500 and guilds / shard_count > 0.8:
            raise ShardingRequired('Too many shards. '
                                   f'(g={guilds} sc={shard_count})')

        if current_shard > shard_count:
            raise InvalidShard('Shard count > Total shards')

    async def handle_1(self, payload: Dict[str, Any]):
        """Handle OP 1 Heartbeat packets."""
        pass

    async def handle_2(self, payload: Dict[str, Any]):
        """Handle the OP 2 Identify packet."""
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
            user_id = await raw_token_check(token, self.ext.db)
        except (Unauthorized, Forbidden):
            raise WebsocketClose(4004, 'Authentication failed')

        bot = await self.ext.db.fetchval("""
        SELECT bot FROM users
        WHERE id = $1
        """, user_id)

        self.state = GatewayState(
            user_id=user_id,
            bot=bot,
            properties=properties,
            compress=compress,
            large=large,
            shard=shard,
            current_shard=shard[0],
            shard_count=shard[1],
            presence=presence,
            ws=self
        )

        await self._check_shards()

        self.ext.state_manager.insert(self.state)
        await self.dispatch_ready()

    async def handle_3(self, payload: Dict[str, Any]):
        """Handle OP 3 Status Update."""
        pass

    async def handle_6(self, payload: Dict[str, Any]):
        """Handle OP 6 Resume."""
        data = payload['d']

        try:
            token, sess_id, seq = data['token'], \
                data['session_id'], data['seq']
        except KeyError:
            raise DecodeError('Invalid resume payload')

        try:
            user_id = await raw_token_check(token, self.ext.db)
        except (Unauthorized, Forbidden):
            raise WebsocketClose(4004, 'Invalid token')

        try:
            state = self.ext.state_manager.fetch(user_id, sess_id)
        except KeyError:
            return await self.send({
                'op': 9,
                'd': False,
            })

        if seq > state.seq:
            raise WebsocketClose(4007, 'Invalid seq')

        # check if a websocket isnt on that state already
        if state.ws is not None:
            log.info('Resuming failed, websocket already connected')
            return await self.send({
                'op': 9,
                'd': False,
            })

        # relink this connection
        self.state = state
        state.ws = self

        # TODO: resend payloads

        await self.dispatch('RESUMED', {})

    async def handle_12(self, payload: Dict[str, Any]):
        """Handle OP 12 Guild Sync."""
        data = payload['d']

        for _guild_id in data:
            # check if user in guild
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
            raise UnknownOPCode(f'Bad OP code: {op_code}')

        await handler(payload)

    async def listen_messages(self):
        """Listen for messages coming in from the websocket."""
        while True:
            message = await self.ws.recv()
            if len(message) > 4096:
                raise DecodeError('Payload length exceeded')

            payload = self.decoder(message)

            pretty_printed = pprint.pformat(payload)
            log.debug('received message: {}', pretty_printed)

            await self.process_message(payload)

    async def run(self):
        """Wrap listen_messages inside
        a try/except block for WebsocketClose handling."""
        try:
            await self.send_hello()
            await self.listen_messages()
        except websockets.exceptions.ConnectionClosed as err:
            log.warning('Client closed, state={}, err={}', self.state, err)
        except WebsocketClose as err:
            log.warning('closed a client, state={} err={}', self.state, err)

            await self.ws.close(code=err.code, reason=err.reason)
        finally:
            if self.state:
                self.state.ws = None
