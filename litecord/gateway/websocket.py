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

import collections
import asyncio
import pprint
import zlib
import json
from typing import List, Dict, Any
from random import randint

import websockets
from logbook import Logger
import earl

from litecord.auth import raw_token_check
from litecord.enums import RelationshipType, ChannelType
from litecord.schemas import validate, GW_STATUS_UPDATE
from litecord.utils import (
    task_wrapper, LitecordJSONEncoder, yield_chunks
)
from litecord.permissions import get_permissions

from litecord.gateway.opcodes import OP
from litecord.gateway.state import GatewayState

from litecord.errors import (
    WebsocketClose, Unauthorized, Forbidden, BadRequest
)
from litecord.gateway.errors import (
    DecodeError, UnknownOPCode, InvalidShard, ShardingRequired
)

from litecord.storage import int_

log = Logger(__name__)

WebsocketProperties = collections.namedtuple(
    'WebsocketProperties', 'v encoding compress zctx tasks'
)

WebsocketObjects = collections.namedtuple(
    'WebsocketObjects', (
        'db', 'state_manager', 'storage',
        'loop', 'dispatcher', 'presence', 'ratelimiter',
        'user_storage', 'voice'
    )
)


def encode_json(payload) -> str:
    return json.dumps(payload, separators=(',', ':'),
                      cls=LitecordJSONEncoder)


def decode_json(data: str):
    return json.loads(data)


def encode_etf(payload) -> str:
    return earl.pack(payload)


def _etf_decode_dict(data):
    # NOTE: this is a very slow implementation to
    # decode the dictionary.

    if isinstance(data, bytes):
        return data.decode()

    if not isinstance(data, dict):
        return data

    _copy = dict(data)
    result = {}

    for key in _copy.keys():
        # assuming key is bytes rn.
        new_k = key.decode()

        # maybe nested dicts, so...
        result[new_k] = _etf_decode_dict(data[key])

    return result

def decode_etf(data: bytes):
    res = earl.unpack(data)

    if isinstance(res, bytes):
        return data.decode()

    if isinstance(res, dict):
        return _etf_decode_dict(res)

    return res


class GatewayWebsocket:
    """Main gateway websocket logic."""

    def __init__(self, ws, app, **kwargs):
        self.ext = WebsocketObjects(
            app.db, app.state_manager, app.storage, app.loop,
            app.dispatcher, app.presence, app.ratelimiter,
            app.user_storage, app.voice
        )

        self.storage = self.ext.storage
        self.user_storage = self.ext.user_storage
        self.presence = self.ext.presence
        self.ws = ws

        self.wsp = WebsocketProperties(kwargs.get('v'),
                                       kwargs.get('encoding', 'json'),
                                       kwargs.get('compress', None),
                                       zlib.compressobj(),
                                       {})

        log.debug('websocket properties: {!r}', self.wsp)

        self.state = None

        self._set_encoders()

    def _set_encoders(self):
        encoding = self.wsp.encoding

        encodings = {
            'json': (encode_json, decode_json),
            'etf': (encode_etf, decode_etf),
        }

        self.encoder, self.decoder = encodings[encoding]

    async def _chunked_send(self, data: bytes, chunk_size: int):
        """Split data in chunk_size-big chunks and send them
        over the websocket."""
        log.debug('zlib-stream: chunking {} bytes into {}-byte chunks',
                  len(data), chunk_size)

        total_chunks = 0
        for chunk in yield_chunks(data, chunk_size):
            total_chunks += 1
            log.debug('zlib-stream: chunk {}', total_chunks)
            await self.ws.send(chunk)

        log.debug('zlib-stream: sent {} chunks', total_chunks)

    async def _zlib_stream_send(self, encoded):
        """Sending a single payload across multiple compressed
        websocket messages."""

        # compress and flush (for the rest of compressed data + ZLIB_SUFFIX)
        data1 = self.wsp.zctx.compress(encoded)
        data2 = self.wsp.zctx.flush(zlib.Z_FULL_FLUSH)

        log.debug('zlib-stream: length {} -> compressed ({} + {})',
                  len(encoded), len(data1), len(data2))

        if not data1:
            # if data1 is nothing, that might cause problems
            # to clients, since they'll receive an empty message
            data1 = bytes([data2[0]])
            data2 = data2[1:]

            log.debug('zlib-stream: len(data1) == 0, remaking as ({} + {})',
                      len(data1), len(data2))

        # NOTE: the old approach was ws.send(data1 + data2).
        #  I changed this to a chunked send of data1 and data2
        #  because that can bring some problems to the network
        #  since we can be potentially sending a really big packet
        #  as a single message.

        #  clients should handle chunked sends (via detection
        #  of the ZLIB_SUFFIX suffix appended to data2), so
        #  this shouldn't being problems.

        # TODO: the chunks are 1024 bytes, 1KB, is this good enough?
        await self._chunked_send(data1, 1024)
        await self._chunked_send(data2, 1024)

    async def send(self, payload: Dict[str, Any]):
        """Send a payload to the websocket.

        This function accounts for the zlib-stream
        transport method used by Discord.
        """
        encoded = self.encoder(payload)

        if len(encoded) < 2048:
            log.debug('sending\n{}', pprint.pformat(payload))
        else:
            log.debug('sending {}', pprint.pformat(payload))
            log.debug('sending op={} s={} t={} (too big)',
                      payload.get('op'),
                      payload.get('s'),
                      payload.get('t'))

        if not isinstance(encoded, bytes):
            encoded = encoded.encode()

        if self.wsp.compress == 'zlib-stream':
            await self._zlib_stream_send(encoded)
        elif self.state and self.state.compress and len(encoded) > 1024:
            # TODO: should we only compress on >1KB packets? or maybe we
            # should do all?
            await self.ws.send(zlib.compress(encoded))
        else:
            await self.ws.send(encoded.decode())

    async def send_op(self, op_code: int, data: Any):
        """Send a packet but just the OP code information is filled in."""
        await self.send({
            'op': op_code,
            'd': data,

            't': None,
            's': None
        })

    def _check_ratelimit(self, key: str, ratelimit_key):
        ratelimit = self.ext.ratelimiter.get_ratelimit(f'_ws.{key}')
        bucket = ratelimit.get_bucket(ratelimit_key)
        return bucket.update_rate_limit()

    async def _hb_wait(self, interval: int):
        """Wait heartbeat"""
        # if the client heartbeats in time,
        # this task will be cancelled.
        await asyncio.sleep(interval / 1000)
        await self.ws.close(4000, 'Heartbeat expired')

        self._cleanup()

    def _hb_start(self, interval: int):
        # always refresh the heartbeat task
        # when possible
        task = self.wsp.tasks.get('heartbeat')
        if task:
            task.cancel()

        self.wsp.tasks['heartbeat'] = self.ext.loop.create_task(
            task_wrapper('hb wait', self._hb_wait(interval))
        )

    async def send_hello(self):
        """Send the OP 10 Hello packet over the websocket."""
        # random heartbeat intervals
        interval = randint(40, 46) * 1000

        await self.send_op(OP.HELLO, {
            'heartbeat_interval': interval,
            '_trace': [
                'lesbian-server'
            ],
        })

        self._hb_start(interval)

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

        log.debug('sending payload {!r} sid {}',
                  event.upper(), self.state.session_id)

        await self.send(payload)

    async def _make_guild_list(self) -> List[Dict[str, Any]]:
        user_id = self.state.user_id

        guild_ids = await self._guild_ids()

        if self.state.bot:
            return [{
                'id': row,
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

    async def _guild_dispatch(self, unavailable_guilds: List[Dict[str, Any]]):
        """Dispatch GUILD_CREATE information."""

        # Users don't get asynchronous guild dispatching.
        if not self.state.bot:
            return

        for guild_obj in unavailable_guilds:
            # fetch full guild object including the 'large' field
            guild = await self.storage.get_guild_full(
                int(guild_obj['id']), self.state.user_id, self.state.large
            )

            if guild is None:
                continue

            await self.dispatch('GUILD_CREATE', guild)

    async def _user_ready(self) -> dict:
        """Fetch information about users in the READY packet.

        This part of the API is completly undocumented.
        PLEAS DISCORD DO NOT BAN ME
        """

        user_id = self.state.user_id

        relationships = await self.user_storage.get_relationships(user_id)

        friend_ids = [int(r['user']['id']) for r in relationships
                      if r['type'] == RelationshipType.FRIEND.value]

        friend_presences = await self.ext.presence.friend_presences(friend_ids)
        settings = await self.user_storage.get_user_settings(user_id)

        return {
            'user_settings': settings,
            'notes': await self.user_storage.fetch_notes(user_id),
            'relationships': relationships,
            'presences': friend_presences,
            'read_state': await self.user_storage.get_read_state(user_id),
            'user_guild_settings': await self.user_storage.get_guild_settings(
                user_id),

            'friend_suggestion_count': 0,


            'connected_accounts': [],
            'experiments': [],
            'guild_experiments': [],
            'analytics_token': 'transbian',
        }

    async def dispatch_ready(self):
        """Dispatch the READY packet for a connecting account."""
        guilds = await self._make_guild_list()

        user_id = self.state.user_id
        user = await self.storage.get_user(user_id, True)

        uready = {}
        if not self.state.bot:
            # user, fetch info
            uready = await self._user_ready()

        private_channels = (
            await self.user_storage.get_dms(user_id) + 
            await self.user_storage.get_gdms(user_id)
        )

        await self.dispatch('READY', {**{
            'v': 6,
            'user': user,

            'private_channels': private_channels,

            'guilds': guilds,
            'session_id': self.state.session_id,
            '_trace': ['transbian']
        }, **uready})

        # async dispatch of guilds
        self.ext.loop.create_task(self._guild_dispatch(guilds))

    async def _check_shards(self, shard, user_id):
        current_shard, shard_count = shard

        guilds = await self.ext.db.fetchval("""
        SELECT COUNT(*)
        FROM members
        WHERE user_id = $1
        """, user_id)

        recommended = max(int(guilds / 1200), 1)

        if shard_count < recommended:
            raise ShardingRequired('Too many guilds for shard '
                                   f'{current_shard}')

        if guilds > 2500 and guilds / shard_count > 0.8:
            raise ShardingRequired('Too many shards. '
                                   f'(g={guilds} sc={shard_count})')

        if current_shard > shard_count:
            raise InvalidShard('Shard count > Total shards')

    async def _guild_ids(self) -> list:
        """Get a list of Guild IDs that are tied to this connection.

        The implementation is shard-aware.
        """
        guild_ids = await self.user_storage.get_user_guilds(
            self.state.user_id
        )

        shard_id = self.state.current_shard
        shard_count = self.state.shard_count

        def _get_shard(guild_id):
            return (guild_id >> 22) % shard_count

        filtered = filter(
            lambda guild_id: _get_shard(guild_id) == shard_id,
            guild_ids
        )

        return list(filtered)

    async def subscribe_all(self):
        """Subscribe to all guilds, DM channels, and friends.

        Note: subscribing to channels is already handled
            by GuildDispatcher.sub
        """
        user_id = self.state.user_id
        guild_ids = await self._guild_ids()

        # subscribe the user to all dms they have OPENED.
        dms = await self.user_storage.get_dms(user_id)
        dm_ids = [int(dm['id']) for dm in dms]

        # fetch all group dms the user is a member of.
        gdm_ids = await self.user_storage.get_gdms_internal(user_id)

        log.info('subscribing to {} guilds', len(guild_ids))
        log.info('subscribing to {} dms', len(dm_ids))
        log.info('subscribing to {} group dms', len(gdm_ids))

        await self.ext.dispatcher.mass_sub(user_id, [
            ('guild', guild_ids),
            ('channel', dm_ids),
            ('channel', gdm_ids)
        ])

        if not self.state.bot:
            # subscribe to all friends
            # (their friends will also subscribe back
            #  when they come online)
            friend_ids = await self.user_storage.get_friend_ids(user_id)
            log.info('subscribing to {} friends', len(friend_ids))
            await self.ext.dispatcher.sub_many('friend', user_id, friend_ids)

    async def update_status(self, status: dict):
        """Update the status of the current websocket connection."""
        if not self.state:
            return

        if self._check_ratelimit('presence', self.state.session_id):
            # Presence Updates beyond the ratelimit
            # are just silently dropped.
            return

        default_status = {
            'afk': False,

            # TODO: fetch status from settings
            'status': 'online',
            'game': None,

            # TODO: this
            'since': 0,
        }

        status = {**(status or {}), **default_status}

        try:
            status = validate(status, GW_STATUS_UPDATE)
        except BadRequest as err:
            log.warning(f'Invalid status update: {err}')
            return

        # try to extract game from activities
        # when game not provided
        if not status.get('game'):
            try:
                game = status['activities'][0]
            except (KeyError, IndexError):
                game = None
        else:
            game = status['game']

        # construct final status
        status = {
            'afk': status.get('afk', False),
            'status': status.get('status', 'online'),
            'game': game,
            'since': status.get('since', 0),
        }

        self.state.presence = status
        log.info(f'Updating presence status={status["status"]} for '
                 f'uid={self.state.user_id}')
        await self.ext.presence.dispatch_pres(self.state.user_id,
                                              self.state.presence)

    async def handle_1(self, payload: Dict[str, Any]):
        """Handle OP 1 Heartbeat packets."""
        # give the client 3 more seconds before we
        # close the websocket
        self._hb_start((46 + 3) * 1000)
        cliseq = payload.get('d')

        if self.state:
            self.state.last_seq = cliseq

        await self.send_op(OP.HEARTBEAT_ACK, None)

    async def _connect_ratelimit(self, user_id: int):
        if self._check_ratelimit('connect', user_id):
            await self.invalidate_session(False)
            raise WebsocketClose(4009, 'You are being ratelimited.')

        if self._check_ratelimit('session', user_id):
            await self.invalidate_session(False)
            raise WebsocketClose(4004, 'Websocket Session Ratelimit reached.')

    async def handle_2(self, payload: Dict[str, Any]):
        """Handle the OP 2 Identify packet."""
        try:
            data = payload['d']
            token = data['token']
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

        await self._connect_ratelimit(user_id)

        bot = await self.ext.db.fetchval("""
        SELECT bot FROM users
        WHERE id = $1
        """, user_id)

        await self._check_shards(shard, user_id)

        # only create a state after checking everything
        self.state = GatewayState(
            user_id=user_id,
            bot=bot,
            compress=compress,
            large=large,
            shard=shard,
            current_shard=shard[0],
            shard_count=shard[1],
            ws=self
        )

        # link the state to the user
        self.ext.state_manager.insert(self.state)

        await self.update_status(presence)
        await self.subscribe_all()
        await self.dispatch_ready()

    async def handle_3(self, payload: Dict[str, Any]):
        """Handle OP 3 Status Update."""
        presence = payload['d']

        # update_status will take care of validation and
        # setting new presence to state
        await self.update_status(presence)

    def voice_key(self, channel_id: int, guild_id: int):
        """Voice state key."""
        return (self.state.user_id, self.state.session_id)

    async def _vsu_get_prop(self, state, data):
        """Get voice state properties from data, fallbacking to
        user settings."""
        try:
            # TODO: fetch from settings if not provided
            self_deaf = bool(data['self_deaf'])
            self_mute = bool(data['self_mute'])
        except (KeyError, ValueError):
            pass

        return {
            'deaf': state.deaf,
            'mute': state.mute,
            'self_deaf': self_deaf,
            'self_mute': self_mute,
        }

    async def handle_4(self, payload: Dict[str, Any]):
        """Handle OP 4 Voice Status Update."""
        data = payload['d']

        if not self.state:
            return

        channel_id = int_(data.get('channel_id'))
        guild_id = int_(data.get('guild_id'))

        # if its null and null, disconnect the user from any voice
        # TODO: maybe just leave from DMs? idk...
        if channel_id is None and guild_id is None:
            return await self.ext.voice.leave_all(self.state.user_id)

        # if guild is not none but channel is, we are leaving
        # a guild's channel
        if channel_id is None:
            return await self.ext.voice.leave(guild_id, self.state.user_id)

        # fetch an existing state given user and guild OR user and channel
        chan_type = ChannelType(
            await self.storage.get_chan_type(channel_id)
        )

        state_id2 = channel_id

        if chan_type == ChannelType.GUILD_VOICE:
            state_id2 = guild_id

        # a voice state key is a Tuple[int, int]
        #  - [0] is the user id
        #  - [1] is the channel id or guild id

        # the old approach was a (user_id, session_id), but
        # that does not work.

        # this works since users can be connected to many channels
        # using a single gateway websocket connection. HOWEVER,
        # they CAN NOT enter two channels in a single guild.

        # this state id format takes care of that.
        voice_key = (self.state.user_id, state_id2)
        voice_state = await self.ext.voice.get_state(voice_key)

        if voice_state is None:
            return await self.ext.voice.create_state(voice_key)

        same_guild = guild_id == voice_state.guild_id
        same_channel = channel_id == voice_state.channel_id

        prop = await self._vsu_get_prop(voice_state, data)

        if same_guild and same_channel:
            return await self.ext.voice.update_state(voice_state, prop)

        if same_guild and not same_channel:
            return await self.ext.voice.move_state(voice_state, channel_id)

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
        await self.send_op(OP.INVALID_SESSION, resumable)

        if not resumable and self.state:
            # since the state will be removed from
            # the manager, it will become unreachable
            # when trying to resume.
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
            await self.invalidate_session(False)
            return

        if presences:
            await self.dispatch('PRESENCE_REPLACE', presences)

        await self.dispatch('RESUMED', {})

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

    async def _req_guild_members(self, guild_id, user_ids: List[int],
                                 query: str, limit: int):
        try:
            guild_id = int(guild_id)
        except (TypeError, ValueError):
            return

        limit = limit or 1000
        exists = await self.storage.get_guild(guild_id)

        if not exists:
            return

        # limit user_ids to 1000 possible members
        user_ids = user_ids[:1000]

        # assumption: requesting user_ids means
        # we don't do query.
        if user_ids:
            members = await self.storage.get_member_multi(guild_id, user_ids)
            mids = [m['user']['id'] for m in members]
            not_found = [uid for uid in user_ids if uid not in mids]

            await self.dispatch('GUILD_MEMBERS_CHUNK', {
                'guild_id': str(guild_id),
                'members': members,
                'not_found': not_found,
            })

            return

        # do the search
        result = await self.storage.query_members(guild_id, query, limit)
        await self.dispatch('GUILD_MEMBERS_CHUNK', {
            'guild_id': str(guild_id),
            'members': result
        })

    async def handle_8(self, payload: Dict):
        """Handle OP 8 Request Guild Members."""
        data = payload['d']
        gids = data['guild_id']

        uids, query, limit = data.get('user_ids', []), \
            data.get('query', ''), \
            data.get('limit', 0)

        if isinstance(gids, str):
            await self._req_guild_members(gids, uids, query, limit)
            return

        for gid in gids:
            # ignore uids on multiple guilds
            await self._req_guild_members(gid, [], query, limit)

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

        gids = await self.user_storage.get_user_guilds(
            self.state.user_id)

        for guild_id in data:
            try:
                guild_id = int(guild_id)
            except (ValueError, TypeError):
                continue

            # check if user in guild
            if guild_id not in gids:
                continue

            await self._guild_sync(guild_id)

    async def handle_13(self, payload: Dict[str, Any]):
        """Handle CALL_SYNC request.

        There isn't any need to actually finish the implementation
        since we don't have voice. Discord doesn't seem to send anything
        on text-only DMs, so I'll keep that behavior and do nothing.

        CALL_SYNC structure (for now, we don't know if there is anything else):
        {
            channel_id: snowflake
        }
        """
        pass

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

        group_id = 'online' | 'offline' | role_id (string)

        sync_item = {
            'group': {
                'id': group_id,
                'count': num
            }
        } | {
            'member': member_object
        }

        list_op = 'SYNC' | 'INVALIDATE' | 'INSERT' | 'UPDATE' | 'DELETE'

        list_data = {
            'id': channel_id | 'everyone',
            'guild_id': guild_id,

            'ops': [
                {
                    'op': list_op,

                    // exists if op = 'SYNC' or 'INVALIDATE'
                    'range': [num, num],

                    // exists if op = 'SYNC'
                    'items': sync_item[],

                    // exists if op == 'INSERT' | 'DELETE' | 'UPDATE'
                    'index': num,

                    // exists if op == 'INSERT' | 'UPDATE'
                    'item': sync_item,
                }
            ],

            // maybe those represent roles that show people
            // separately from the online list?
            'groups': [
                {
                    'id': group_id
                    'count': num
                }, ...
            ]
        }
        """
        data = payload['d']

        gids = await self.user_storage.get_user_guilds(self.state.user_id)
        guild_id = int(data['guild_id'])

        # make sure to not extract info you shouldn't get
        if guild_id not in gids:
            return

        log.debug('lazy request: members: {}',
                  data.get('members', []))

        # make shard query
        lazy_guilds = self.ext.dispatcher.backends['lazy_guild']

        for chan_id, ranges in data.get('channels', {}).items():
            chan_id = int(chan_id)
            member_list = await lazy_guilds.get_gml(chan_id)

            perms = await get_permissions(
                self.state.user_id, chan_id, storage=self.storage)

            if not perms.bits.read_messages:
                # ignore requests to unknown channels
                return

            await member_list.shard_query(
                self.state.session_id, ranges
            )

    async def process_message(self, payload):
        """Process a single message coming in from the client."""
        try:
            op_code = payload['op']
        except KeyError:
            raise UnknownOPCode('No OP code')

        try:
            handler = getattr(self, f'handle_{op_code}')
        except AttributeError:
            log.warning('Payload with bad op: {}', pprint.pformat(payload))
            raise UnknownOPCode(f'Bad OP code: {op_code}')

        await handler(payload)

    async def _msg_ratelimit(self):
        if self._check_ratelimit('messages', self.state.session_id):
            raise WebsocketClose(4008, 'You are being ratelimited.')

    async def listen_messages(self):
        """Listen for messages coming in from the websocket."""

        # close anyone trying to login while the
        # server is shutting down
        if self.ext.state_manager.closed:
            raise WebsocketClose(4000, 'state manager closed')

        if not self.ext.state_manager.accept_new:
            raise WebsocketClose(4000, 'state manager closed for new')

        while True:
            message = await self.ws.recv()
            if len(message) > 4096:
                raise DecodeError('Payload length exceeded')

            if self.state:
                await self._msg_ratelimit()

            payload = self.decoder(message)
            await self.process_message(payload)

    def _cleanup(self):
        for task in self.wsp.tasks.values():
            task.cancel()

        if self.state:
            self.ext.state_manager.remove(self.state)
            self.state.ws = None
            self.state = None

    async def _check_conns(self, user_id):
        """Check if there are any existing connections.

        If there aren't, dispatch a presence for offline.
        """
        if not user_id:
            return

        # TODO: account for sharding
        # this only updates status to offline once
        # ALL shards have come offline
        states = self.ext.state_manager.user_states(user_id)
        with_ws = [s for s in states if s.ws]

        # there arent any other states with websocket
        if not with_ws:
            offline = {
                'afk': False,
                'status': 'offline',
                'game': None,
                'since': 0,
            }

            await self.ext.presence.dispatch_pres(
                user_id,
                offline
            )

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
            user_id = self.state.user_id if self.state else None
            self._cleanup()
            await self._check_conns(user_id)
