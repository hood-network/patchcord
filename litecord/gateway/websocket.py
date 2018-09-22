import json
import collections
import pprint
import zlib
from typing import List, Dict, Any
from random import randint

import earl
import websockets
from logbook import Logger

from litecord.errors import WebsocketClose, Unauthorized, Forbidden
from litecord.auth import raw_token_check
from .errors import DecodeError, UnknownOPCode, \
    InvalidShard, ShardingRequired
from .opcodes import OP
from .state import GatewayState

from ..schemas import validate, GW_STATUS_UPDATE


log = Logger(__name__)
WebsocketProperties = collections.namedtuple(
    'WebsocketProperties', 'v encoding compress zctx'
)

WebsocketObjects = collections.namedtuple(
    'WebsocketObjects', 'db state_manager storage loop dispatcher presence'
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
        self.presence = self.ext.presence
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
        log.debug('sending {}', pprint.pformat(payload))
        encoded = self.encoder(payload)

        if not isinstance(encoded, bytes):
            encoded = encoded.encode()

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
                # random heartbeat intervals
                'heartbeat_interval': randint(40, 46) * 1000,
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
                **await self.storage.get_guild(guild_id, user_id),
                **await self.storage.get_guild_extra(guild_id, user_id,
                                                     self.state.large)
            }
            for guild_id in guild_ids
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
            # TODO
            'relationships': [],

            # TODO
            'user_guild_settings': [],

            # TODO
            'notes': {},
            'friend_suggestion_count': 0,

            # TODO
            'presences': [],

            # TODO
            'read_state': [],

            'experiments': [],
            'guild_experiments': [],

            # TODO
            'connected_accounts': [],

            # TODO: make those changeable
            'user_settings': {
                'afk_timeout': 300,
                'animate_emoji': True,
                'convert_emoticons': False,
                'default_guilds_restricted': True,
                'detect_platform_accounts': False,
                'developer_mode': True,
                'disable_games_tab': True,
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

            # TODO: dms
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

    async def _guild_ids(self):
        # TODO: account for sharding
        guild_ids = await self.ext.db.fetch("""
        SELECT guild_id
        FROM members
        WHERE user_id = $1
        """, self.state.user_id)

        return [r['guild_id'] for r in guild_ids]

    async def subscribe_guilds(self):
        """Subscribe to all available guilds"""
        guild_ids = await self._guild_ids()
        self.ext.dispatcher.sub_many(self.state.user_id, guild_ids)

    async def update_status(self, status: dict):
        if status is None:
            status = {
                'afk': False,

                # TODO: fetch status from settings
                'status': 'online',
                'game': None,

                # TODO: this
                'since': 0,
            }

            self.state.presence = status

        status = validate(status, GW_STATUS_UPDATE, False)

        if not status:
            # invalid status, must ignore
            return

        self.state.presence = status
        await self.ext.presence.dispatch_pres(self.state.user_id,
                                              self.state.presence)

    async def handle_1(self, payload: Dict[str, Any]):
        """Handle OP 1 Heartbeat packets."""
        # TODO: handling heartbeats
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
            ws=self
        )

        await self._check_shards()

        self.ext.state_manager.insert(self.state)
        await self.dispatch_ready()
        await self.subscribe_guilds()

        # dispatch presence only after subscribing
        await self.update_status(presence)

    async def handle_3(self, payload: Dict[str, Any]):
        """Handle OP 3 Status Update."""
        presence = payload['d']

        # update_status will take care of validation and
        # setting new presence to state
        await self.update_status(presence)

    async def handle_4(self, payload: Dict[str, Any]):
        """Handle OP 4 Voice Status Update."""
        pass

    async def _handle_5(self, payload: Dict[str, Any]):
        """Handle OP 5 Voice Server Ping.

        packet's data structure:

        {
            delay: num,
            speaking: num,
            ssrc: num
        }

        """
        pass

    async def invalidate_session(self, resumable: bool = True):
        """Invalidate the current session and signal that
        to the client."""
        await self.send({
            'op': OP.INVALID_SESSION,
            'd': resumable,
        })

        if not resumable and self.state:
            self.ext.state_manager.remove(self.state)

    async def _resume(self, replay_seqs: iter):
        presences = []

        try:
            for seq in replay_seqs:
                try:
                    payload = self.state.store[seq]
                except KeyError:
                    # ignore unknown seqs
                    continue

                payload_t = payload.get('t')

                # presence resumption happens
                # on a separate event, PRESENCE_REPLACE.
                if payload_t == 'PRESENCE_UPDATE':
                    presences.append(payload.get('d'))
                    continue

                await self.send(payload)
        except Exception:
            log.exception('error while resuming')
            await self.invalidate_session()
            return

        if presences:
            await self.dispatch('PRESENCE_REPLACE', presences)

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
            return await self.invalidate_session(False)

        if seq > state.seq:
            raise WebsocketClose(4007, 'Invalid seq')

        # check if a websocket isnt on that state already
        if state.ws is not None:
            log.info('Resuming failed, websocket already connected')
            return await self.invalidate_session(False)

        # relink this connection
        self.state = state
        state.ws = self

        await self._resume(range(seq, state.seq))
        await self.dispatch('RESUMED', {})

    async def _guild_sync(self, guild_id: int):
        members = await self.storage.get_member_data(guild_id)
        member_ids = [int(m['user']['id']) for m in members]

        log.debug(f'Syncing guild {guild_id} with {len(member_ids)} members')
        presences = await self.presence.guild_presences(member_ids, guild_id)

        await self.dispatch('GUILD_SYNC', {
            'id': str(guild_id),
            'presences': presences,
            'members': members,
        })

    async def handle_12(self, payload: Dict[str, Any]):
        """Handle OP 12 Guild Sync."""
        data = payload['d']

        gids = await self.storage.get_user_guilds(self.state.user_id)

        for guild_id in data:
            try:
                guild_id = int(guild_id)
            except (ValueError, TypeError):
                continue

            # check if user in guild
            if guild_id not in gids:
                continue

            await self._guild_sync(guild_id)

    async def handle_14(self, payload: Dict[str, Any]):
        """Lazy guilds handler.

        This is the known structure of an OP 14:

        lazy_request = {
            'guild_id': guild_id,
            'channels': {
                // the client wants a specific range of members
                // from the channel. so you must assume each query is
                // for people with roles that can Read Messages
                channel_id -> [[min, max], ...],
                ...
            },

            'members': [?], // ???
            'activities': bool, // ???
            'typing': bool, // ???
        }

        This is the known structure of GUILD_MEMBER_LIST_UPDATE:

        sync_item = {
            'group': {
                'id': string, // 'online' | 'offline' | any role id
                'count': num
            }
        } | {
            'member': member_object
        }

        list_op = 'SYNC' | 'INVALIDATE' | 'INSERT' | 'UPDATE' | 'DELETE'

        list_data = {
            'id': "everyone" // ??
            'guild_id': guild_id,

            'ops': [
                {
                    'op': list_op,

                    // exists if op = 'SYNC' or 'INVALIDATE'
                    'range': [num, num],

                    // exists if op = 'SYNC'
                    'items': sync_item[],

                    // exists if op = 'INSERT' or 'DELETE'
                    'index': num,

                    // exists if op = 'INSERT'
                    'item': sync_item,
                }
            ],

            // maybe those represent roles that show people
            // separately from the online list?
            'groups': [
                {
                    'id': string // 'online' | 'offline' | any role id
                    'count': num
                }, ...
            ]
        }

        # Implementation defails.

        Lazy guilds are complicated to deal with in the backend level
        as there are a lot of computation to be done for each request.

        The current implementation is rudimentary and does not account
        for any roles inside the guild.

        A correct implementation would take account of roles and make
        the correct groups on list_data:

        For each channel in lazy_request['channels']:
         - get all roles that have Read Messages on the channel:
           - Also fetch their member counts, as it'll be important
         - with the role list, order them like you normally would
            (by their role priority)
         - based on the channel's range's min and max and the ordered
            role list, you can get the roles wanted for your list_data reply.
         - make new groups ONLY when the role is hoisted.
        """
        data = payload['d']

        gids = await self.storage.get_user_guilds(self.state.user_id)
        guild_id = int(data['guild_id'])

        # make sure to not extract info you shouldn't get
        if guild_id not in gids:
            return

        members = await self.storage.get_member_data(guild_id)
        member_ids = [int(m['user']['id']) for m in members]

        # the current implementation is rudimentary and only
        # generates two groups: online and offline, using
        # guild_presences for list_data.

        # this also doesn't take account the channels in lazy_request.

        guild_presences = await self.presence.guild_presences(member_ids,
                                                              guild_id)

        online = [{'member': p}
                  for p in guild_presences
                  if p['status'] == 'online']
        offline = [{'member': p}
                   for p in guild_presences
                   if p['status'] == 'offline']

        # construct items in the WORST WAY POSSIBLE.
        items = [{
            'group': {
                'id': 'online',
                'count': len(online),
            }
        }] + online + [{
            'group': {
                'id': 'offline',
                'count': len(offline),
            }
        }] + offline

        await self.dispatch('GUILD_MEMBER_LIST_UPDATE', {
            'id': 'everyone',
            'guild_id': data['guild_id'],
            'groups': [
                {
                    'id': 'online',
                    'count': len(online),
                },
                {
                    'id': 'offline',
                    'count': len(offline),
                }
            ],

            'ops': [
                {
                    'range': [0, 99],
                    'op': 'SYNC',
                    'items': items
                }
            ]
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
            raise UnknownOPCode(f'Bad OP code: {op_code}')

        await handler(payload)

    async def listen_messages(self):
        """Listen for messages coming in from the websocket."""
        while True:
            message = await self.ws.recv()
            if len(message) > 4096:
                raise DecodeError('Payload length exceeded')

            payload = self.decoder(message)

            log.debug('received message: {}',
                      pprint.pformat(payload))

            await self.process_message(payload)

    async def run(self):
        """Wrap listen_messages inside
        a try/except block for WebsocketClose handling."""
        try:
            await self.send_hello()
            await self.listen_messages()
        except websockets.exceptions.ConnectionClosed as err:
            log.warning('conn close, state={}, err={}', self.state, err)
        except WebsocketClose as err:
            log.warning('ws close, state={} err={}', self.state, err)

            await self.ws.close(code=err.code, reason=err.reason)
        except Exception as err:
            log.exception('An exception has occoured. state={}', self.state)
            await self.ws.close(code=4000, reason=repr(err))
        finally:
            # TODO: move this to a heartbeat checker
            # instead of websocket cleanup
            self.ext.state_manager.remove(self.state)

            # disconnect the state from the websocket
            if self.state:
                self.state.ws = None
