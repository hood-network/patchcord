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

import collections
import asyncio
import pprint
import zlib
import time
from typing import List, Dict, Any, Iterable, Optional, TYPE_CHECKING
from random import randint

import websockets
import zstandard as zstd
from logbook import Logger

from litecord.auth import raw_token_check
from litecord.enums import RelationshipType, ChannelType, ActivityType, Intents
from litecord.utils import (
    task_wrapper,
    yield_chunks,
    maybe_int,
    custom_status_to_activity,
    custom_status_is_expired,
    custom_status_set_null,
    want_bytes,
    want_string,
    index_by_func,
)
from litecord.permissions import get_permissions
from litecord.presence import BasePresence

from litecord.gateway.opcodes import OP
from litecord.gateway.state import GatewayState
from litecord.errors import WebsocketClose, Unauthorized, Forbidden, BadRequest
from litecord.gateway.errors import (
    GatewayError,
    UnknownOPCode,
    InvalidShard,
    ShardingRequired,
)
from litecord.gateway.encoding import encode_json, decode_json, encode_etf, decode_etf
from litecord.gateway.utils import WebsocketFileHandler
from litecord.gateway.schemas import (
    validate,
    IDENTIFY_SCHEMA,
    GW_STATUS_UPDATE,
    RESUME_SCHEMA,
    REQ_GUILD_SCHEMA,
    GUILD_SYNC_SCHEMA,
)

from litecord.storage import int_

from litecord.blueprints.gateway import get_gw

if TYPE_CHECKING:
    from litecord.typing_hax import app
else:
    from quart import current_app as app

log = Logger(__name__)

WebsocketProperties = collections.namedtuple(
    "WebsocketProperties", "version encoding compress zctx zsctx tasks"
)


def _complete_users_list(user_id: str, base_ready, user_ready, ws_properties) -> dict:
    """Use the data we were already preparing to send in READY to construct
    the users array, saving on I/O cost."""

    users_to_send = {}

    for private_channel in base_ready["private_channels"]:
        for recipient in private_channel["recipients"]:
            users_to_send[recipient["id"]] = recipient

    user_relationships = user_ready.get("relationships", [])
    for relationship in user_relationships:
        relationship_user = relationship["user"]
        users_to_send[relationship_user["id"]] = relationship_user

    ready = {**base_ready, **user_ready}
    ready["users"] = [value for value in users_to_send.values()]

    # for relationship in ready["relationships"]:
    #     relationship["user_id"] = relationship["user"]["id"]

    for private_channel in ready["private_channels"]:
        if private_channel["type"] == 1:
            self_user_index = index_by_func(
                lambda user: user["id"] == str(user_id), private_channel["recipients"]
            )
            if ws_properties.version > 7:
                assert self_user_index is not None
                private_channel["recipients"].pop(self_user_index)
            else:
                if self_user_index == 0:
                    private_channel["recipients"].append(
                        private_channel["recipients"].pop(0)
                    )

        # if ws_properties.version >= 9:
        #     private_channel["recipient_ids"] = [recipient["id"] for recipient in private_channel["recipients"]],

    return ready, users_to_send


async def _compute_supplemental(app, base_ready, user_ready, users_to_send: dict):
    supplemental = {
        "merged_presences": {"guilds": [], "friends": []},
        "merged_members": [],
        "guilds": [],
        "lazy_private_channels": [],
    }

    supplemental["merged_presences"]["friends"] = [{**presence, "last_modified": 0} for presence in user_ready["presences"]]

    for guild in base_ready["guilds"]:
        if not guild.get("unavailable"):
            supplemental["guilds"].append(
                {
                    "voice_states": await app.storage.guild_voice_states(int(guild["id"])),
                    "embedded_activities": [],
                    "id": guild["id"],
                }
            )
        else:
            # Yes, this is how Discord does it
            supplemental["guilds"].append({"id": guild["id"]})

        supplemental["merged_presences"]["guilds"].append(guild.get("presences", guild.get("presence", [])))
        supplemental["merged_members"].append(guild.get("members"))

    return supplemental


def calculate_intents(data) -> Intents:
    intents_int = data.get("intents")
    guild_subscriptions = data.get("guild_subscriptions")
    if guild_subscriptions is False and intents_int is None:
        intents_int = Intents(0)
        intents_int |= Intents.GUILD_MESSAGE_TYPING
        intents_int |= Intents.DIRECT_MESSAGE_TYPING
        intents_int |= Intents.GUILD_PRESENCES
        intents_int |= Intents.GUILD_MEMBERS
        intents_int = ~intents_int
    elif intents_int is None:
        intents_int = Intents.default()

    return Intents(intents_int)


class GatewayWebsocket:
    """Main gateway websocket logic."""

    def __init__(self, ws, *, version, encoding, compress):
        self.app = app
        self.storage = app.storage
        self.user_storage = app.user_storage
        self.presence = app.presence
        self.ws = ws

        self.ws_properties = WebsocketProperties(
            version,
            encoding,
            compress,
            zlib.compressobj(),
            zstd.ZstdCompressor(),
            {},
        )
        self.ready = asyncio.Event()

        log.debug("websocket properties: {!r}", self.ws_properties)

        self.state = None
        self._hb_counter = 0

        self._set_encoders()

    def _set_encoders(self):
        encoding = self.ws_properties.encoding

        encodings = {
            "json": (encode_json, decode_json),
            "etf": (encode_etf, decode_etf),
        }

        self.encoder, self.decoder = encodings[encoding]

    async def _chunked_send(self, data: bytes, chunk_size: int):
        """Split data in chunk_size-big chunks and send them
        over the websocket."""
        log.debug(
            "zlib-stream: sending {} bytes into {}-byte chunks", len(data), chunk_size
        )

        # we send the entire iterator as per websockets documentation
        # to pretent setting FIN when we don't want to
        # see https://gitlab.com/litecord/litecord/-/issues/139
        await self.ws.send(yield_chunks(data, chunk_size))

    async def _zlib_stream_send(self, encoded):
        """Sending a single payload across multiple compressed
        websocket messages."""

        # compress and flush (for the rest of compressed data + ZLIB_SUFFIX)
        data1 = self.ws_properties.zctx.compress(encoded)
        data2 = self.ws_properties.zctx.flush(zlib.Z_FULL_FLUSH)
        data = data1 + data2

        log.debug(
            "zlib-stream: length {} -> compressed ({})",
            len(encoded),
            len(data),
        )

        # since we always chunk the entire compressed message, we shouldn't
        # worry about sending big frames to the clients

        # TODO: the chunks are 1024 bytes, 1KB, is this good enough?
        await self._chunked_send(data, 1024)

    async def _zstd_stream_send(self, encoded):
        compressor = self.ws_properties.zsctx.stream_writer(
            WebsocketFileHandler(self.ws)
        )

        compressor.write(encoded)
        compressor.flush(zstd.FLUSH_FRAME)

    async def send(self, payload: Dict[str, Any]):
        """Send a payload to the websocket.

        This function accounts for the zlib-stream
        transport method used by Discord.
        """
        encoded = self.encoder(payload)

        if len(encoded) < 2048:
            log.debug("sending\n{}", pprint.pformat(payload))
        else:
            log.debug("sending {}", pprint.pformat(payload))
            log.debug(
                "sending op={} s={} t={} (too big)",
                payload.get("op"),
                payload.get("s"),
                payload.get("t"),
            )

        # TODO encode to bytes only when absolutely needed e.g
        # when compressing, because encoding == json means bytes won't work
        if isinstance(encoded, str):
            encoded = encoded.encode()

        if self.ws_properties.compress == "zlib-stream":
            await self._zlib_stream_send(want_bytes(encoded))
        elif self.ws_properties.compress == "zstd-stream":
            await self._zstd_stream_send(want_bytes(encoded))
        elif (
            self.state
            and self.state.compress
            and len(encoded) > 8192
            and self.ws_properties.encoding != "etf"
        ):
            # TODO determine better conditions to trigger a compress set
            # by identify
            await self.ws.send(zlib.compress(want_bytes(encoded)))
        else:
            await self.ws.send(
                want_bytes(encoded)
                if self.ws_properties.encoding == "etf"
                else want_string(encoded)
            )

    async def send_op(self, op_code: int, data: Any):
        """Send a packet but just the OP code information is filled in."""
        await self.send({"op": op_code, "d": data, "t": None, "s": None})

    def _check_ratelimit(self, key: str, ratelimit_key):
        ratelimit = self.app.ratelimiter.get_ratelimit(f"_ws.{key}")
        bucket = ratelimit.get_bucket(ratelimit_key)
        return bucket.update_rate_limit()

    async def _hb_wait(self, interval: int):
        """Wait heartbeat"""
        # if the client heartbeats in time,
        # this task will be cancelled.
        await asyncio.sleep(interval / 1000)
        await self.ws.close(4000, "Heartbeat expired")

        self._cleanup()

    def _hb_start(self, interval: int):
        # always refresh the heartbeat task
        # when possible
        task = self.ws_properties.tasks.get("heartbeat")
        if task:
            task.cancel()

        self.ws_properties.tasks["heartbeat"] = app.sched.spawn(
            task_wrapper("hb wait", self._hb_wait(interval))
        )

    async def _send_hello(self):
        """Send the OP 10 Hello packet over the websocket."""
        # random heartbeat intervals
        await self.send_op(
            OP.HELLO, {"heartbeat_interval": 41250, "_trace": ["litecord"]}
        )

        self._hb_start(41250)

    async def dispatch_raw(self, event: str, data: Any):
        """Dispatch an event to the websocket, bypassing the gateway state.

        Only use this function for events related to connection state,
        such as READY and RESUMED, or events that are replies to
        messages in the websocket.
        """
        payload = {
            "op": OP.DISPATCH,
            "t": event.upper(),
            "s": self.state.seq,
            "d": data,
        }

        log.debug("sending payload {!r} sid {}", event.upper(), self.state.session_id)

        try:
            await self.send(payload)
        except websockets.exceptions.ConnectionClosed:
            log.warning(
                "Failed to dispatch {!r} to {}", event.upper, self.state.session_id
            )

    async def _make_guild_list(self) -> List[Dict[str, Any]]:
        assert self.state is not None
        guild_ids = await self._guild_ids()

        if self.state.bot:
            return [{"id": row, "unavailable": True} for row in guild_ids]

        return await self.storage.get_guilds(
            guild_ids, self.state.user_id, True, large=self.state.large
        )

    async def _guild_dispatch(self, unavailable_guilds: List[Dict[str, Any]]):
        """Dispatch GUILD_CREATE information."""
        assert self.state is not None

        # Users don't get asynchronous guild dispatching
        if not self.state.bot:
            return

        guild_ids = [int(g["id"]) for g in unavailable_guilds]
        guilds = await self.storage.get_guilds(
            guild_ids, self.state.user_id, True, large=self.state.large
        )
        for guild in guilds:
            await self.dispatch_raw("GUILD_CREATE", {**guild, "unavailable": False})

    async def _user_ready(self, *, settings=None) -> dict:
        """Fetch information about users in the READY packet."""

        assert self.state is not None
        user_id = self.state.user_id
        relationships = await self.user_storage.get_relationships(user_id)
        friend_users = [
            r["user"]
            for r in relationships
            if r["type"] == RelationshipType.FRIEND.value
        ]

        friend_presences = await self.app.presence.friend_presences(friend_users)
        settings = settings or await self.user_storage.get_user_settings(user_id)

        if self.ws_properties.version < 8:  # v6 and below
            user_guild_settings = await self.user_storage.get_guild_settings(user_id)
            read_state = await self.user_storage.get_read_state(user_id)
        else:
            user_guild_settings = {
                "entries": await self.user_storage.get_guild_settings(user_id),
                "partial": False,
            }
            read_state = {
                "entries": await self.user_storage.get_read_state(user_id),
                "partial": False,
            }

        return {
            "user_settings": settings,
            "notes": await self.user_storage.fetch_notes(user_id),
            "relationships": relationships,
            "presences": friend_presences,
            "read_state": read_state,
            "user_guild_settings": user_guild_settings,
            "friend_suggestion_count": 0,
            "country_code": "US",
            "geo_ordered_rtc_regions": [],
            "experiments": await self.storage.get_experiments(),
            "guild_experiments": await self.storage.get_guild_experiments(),
            "sessions": [
                {
                    "session_id": self.state.session_id,
                    "status": self.state.presence.status,
                    "activities": self.state.presence.activities,
                    "client_info": {"client": "web", "os": "windows", "version": 0},
                }
            ],
            "consents": {"personalization": {"consented": True}},
            "connected_accounts": [],
            "analytics_token": "analytics",
            "users": [],
            "merged_members": [],
            "tutorial": None,
            "lazy_private_channels": [],
        }

    async def dispatch_ready(self, **kwargs):
        """Dispatch the READY packet for a connecting account."""
        guilds = await self._make_guild_list()
        assert self.state is not None

        user_id = self.state.user_id
        user = await self.storage.get_user(user_id, True)

        user_ready = {}
        if not self.state.bot:
            # user, fetch info
            user_ready = await self._user_ready(**kwargs)

        private_channels = await self.user_storage.get_dms(
            user_id
        ) + await self.user_storage.get_gdms(user_id)

        base_ready = {
            "v": self.ws_properties.version,
            "user": user,
            "private_channels": private_channels,
            "guilds": guilds,
            "session_id": self.state.session_id,
            "_trace": ["litecord"],
            "resume_gateway_url": get_gw(),
            "session_type": "normal",
            "user_settings": {},
            "heartbeat_interval": 41250,
        }

        shard = [self.state.current_shard, self.state.shard_count]
        if self.state.shard_count > 1:
            base_ready["shard"] = shard

        if self.state.bot:
            base_ready["application"] = {"id": str(user_id), "flags": 8667136}

        # pass users_to_send to ready_supplemental so that its easier to
        # cross-reference things
        full_ready_data, users_to_send = _complete_users_list(
            user["id"], base_ready, user_ready, self.ws_properties
        )
        ready_supplemental = await _compute_supplemental(
            self.app, base_ready, user_ready, users_to_send
        )

        full_ready_data["merged_members"] = [[member for member in members if member["user"]["id"] == user["id"]] for members in ready_supplemental["merged_members"]]

        if self.ws_properties.version < 6:  # Extremely old client compat
            for guild in full_ready_data["guilds"]:
                guild["presence"] = guild.pop("presences", {})

        # if not self.state.bot:
        #     for guild in full_ready_data["guilds"]:
        #         guild["members"] = []

        await self.dispatch_raw("READY", full_ready_data)
        await self.dispatch_raw("READY_SUPPLEMENTAL", ready_supplemental)
        self.ready.set()
        app.sched.spawn(self._guild_dispatch(guilds))

    async def _check_shards(self, shard, user_id):
        """Check if the given `shard` value in IDENTIFY has good enough values."""
        current_shard, shard_count = shard

        guilds = await self.app.db.fetchval(
            """
        SELECT COUNT(*)
        FROM members
        WHERE user_id = $1
        """,
            user_id,
        )

        recommended = max(int(guilds / 1200), 1)

        if shard_count < recommended:
            raise ShardingRequired(f"Too many guilds for shard {current_shard}.")

        if guilds > 2500 and guilds / shard_count > 0.8:
            raise ShardingRequired("Too many shards.")

        if current_shard > shard_count:
            raise InvalidShard("Invalid shards.")

    async def _guild_ids(self) -> list:
        """Get a list of Guild IDs that are tied to this connection.

        The implementation is shard-aware.
        """
        guild_ids = await self.user_storage.get_user_guilds(self.state.user_id)

        shard_id = self.state.current_shard
        shard_count = self.state.shard_count

        def _get_shard(guild_id):
            return (guild_id >> 22) % shard_count

        filtered = filter(lambda guild_id: _get_shard(guild_id) == shard_id, guild_ids)

        return list(filtered)

    async def subscribe_all(self):
        """Subscribe to all guilds, DM channels, and friends.

        Note: subscribing to channels is already handled
            by GuildDispatcher.sub
        """
        assert self.state is not None
        user_id = self.state.user_id
        guild_ids = await self._guild_ids()

        # subscribe the user to all dms they have OPENED.
        dms = await self.user_storage.get_dms(user_id)
        dm_ids = [int(dm["id"]) for dm in dms]

        # fetch all group dms the user is a member of.
        gdm_ids = await self.user_storage.get_gdms_internal(user_id)

        log.info(
            "subscribing to {} guilds {} dms {} gdms",
            len(guild_ids),
            len(dm_ids),
            len(gdm_ids),
        )

        # guild_subscriptions:
        #  enables dispatching of guild subscription events
        #  (presence and typing events)

        # we enable processing of guild_subscriptions by adding flags
        # when subscribing to the given backend.
        session_id = self.state.session_id
        channel_ids: List[int] = []

        for guild_id in guild_ids:
            _, channels = await app.dispatcher.guild.sub_user(guild_id, user_id)
            channel_ids.extend(channels)

        log.info("subscribing to {} guild channels", len(channel_ids))
        for channel_id in channel_ids:
            await app.dispatcher.channel.sub(channel_id, session_id)

        for dm_id in dm_ids:
            await app.dispatcher.channel.sub(dm_id, session_id)

        for gdm_id in gdm_ids:
            await app.dispatcher.channel.sub(gdm_id, session_id)

        # subscribe to all friends
        # (their friends will also subscribe back
        #  when they come online)
        if not self.state.bot:
            friend_ids = await self.user_storage.get_friend_ids(user_id)
            log.info("subscribing to {} friends", len(friend_ids))
            for friend_id in friend_ids:
                await app.dispatcher.friend.sub(user_id, friend_id)

    async def update_presence(
        self,
        given_presence: dict,
        *,
        settings: Optional[dict] = None,
        override_ratelimit=False,
    ):
        """Update the presence of the current websocket connection.

        Invalid presences are silently dropped. As well as when the state is
        invalid/incomplete.
        When the session is beyond the Status Update's ratelimits, the update
        is silently dropped.
        """
        if not self.state:
            return

        if not override_ratelimit and self._check_ratelimit(
            "presence", self.state.session_id
        ):
            return

        settings = settings or await self.user_storage.get_user_settings(
            self.state.user_id
        )

        presence = BasePresence(status=(settings["status"] or "online"), game=None)

        custom_status = settings.get("custom_status") or None
        if isinstance(custom_status, dict) and custom_status is not None:
            presence.game = await custom_status_to_activity(custom_status)
            if presence.game is None:
                await custom_status_set_null(self.state.user_id)

        log.debug("pres={}, given pres={}", presence, given_presence)

        try:
            given_presence = validate(given_presence, GW_STATUS_UPDATE)
        except BadRequest as err:
            log.warning(f"Invalid status update: {err}")
            return

        presence.update_from_incoming_dict(given_presence)

        # always try to use activities.0 to replace game when possible
        activities: Optional[List[dict]] = given_presence.get("activities")
        try:
            activity: Optional[dict] = (activities or [])[0]
        except IndexError:
            activity = None

        game: Optional[dict] = activity or presence.game

        # hacky, but works (id and created_at aren't documented)
        if game is not None and game["type"] == ActivityType.CUSTOM.value:
            game["id"] = "custom"
            game["created_at"] = int(time.time() * 1000)

            emoji = game.get("emoji") or {}
            if emoji.get("id") is None and emoji.get("name") is not None:
                # drop the other fields when we're using unicode emoji
                game["emoji"] = {"name": emoji["name"]}

        presence.game = game

        if presence.status == "invisible":
            presence.status = "offline"

        if presence.status == "unknown":
            presence.status = "online"

        self.state.presence = presence

        log.info(
            "updating presence status={} for uid={}",
            presence.status,
            self.state.user_id,
        )
        log.debug("full presence = {}", presence)

        await self.dispatch_raw(
            "SESSIONS_REPLACE",
            [
                {
                    "session_id": self.state.session_id,
                    "status": presence.status,
                    "activities": presence.activities,
                    "client_info": {"client": "web", "os": "windows", "version": 0},
                }
            ],
        )
        await self.app.presence.dispatch_pres(self.state.user_id, self.state.presence)

    async def _custom_status_expire_check(self):
        if not self.state:
            return

        settings = await self.user_storage.get_user_settings(self.state.user_id)
        custom_status = settings["custom_status"]
        if custom_status is None:
            return

        if not custom_status_is_expired(custom_status.get("expires_at")):
            return

        await custom_status_set_null(self.state.user_id)
        await self.update_presence(
            {"status": self.state.presence.status, "game": None},
            override_ratelimit=True,
        )

    async def handle_1(self, payload: Dict[str, Any]):
        """Handle OP 1 Heartbeat packets."""
        # give the client 3 more seconds before we
        # close the websocket

        self._hb_counter += 1
        if self._hb_counter % 2 == 0:
            self.app.sched.spawn(self._custom_status_expire_check())

        self._hb_start((46 + 3) * 1000)
        cliseq = payload.get("d")

        if self.state:
            self.state.last_seq = cliseq

        await self.send_op(OP.HEARTBEAT_ACK, None)

    async def _connect_ratelimit(self, user_id: int):
        if self._check_ratelimit("connect", user_id):
            await self.invalidate_session(False)
            raise WebsocketClose(4009, "You are being ratelimited.")

        if self._check_ratelimit("session", user_id) and self.state.bot:
            await self.invalidate_session(False)
            raise WebsocketClose(4004, "Gateway session ratelimit reached.")

    async def handle_2(self, payload: Dict[str, Any]):
        """Handle the OP 2 Identify packet."""
        validate(payload, IDENTIFY_SCHEMA)
        data = payload["d"]
        token = data["token"]

        compress = data.get("compress", False)
        large = data.get("large_threshold", 50)

        shard = data.get("shard", [0, 1])
        presence = data.get("presence") or {}

        if self.ws_properties.version > 7:
            data.pop("guild_subscriptions", None)

        intents = calculate_intents(data)

        try:
            user_id = await raw_token_check(token, self.app.db)
        except (Unauthorized, Forbidden):
            raise WebsocketClose(4004, "Authentication failed")

        await self._connect_ratelimit(user_id)

        bot = await self.app.db.fetchval(
            """
        SELECT bot FROM users
        WHERE id = $1
        """,
            user_id,
        )

        await self._check_shards(shard, user_id)

        # only create a state after checking everything
        self.state = state = GatewayState(
            user_id=user_id,
            bot=bot,
            compress=compress,
            large=large,
            current_shard=shard[0],
            shard_count=shard[1],
            intents=intents,
        )

        state.ws = self

        # link the state to the user
        self.app.state_manager.insert(state)

        settings = await self.user_storage.get_user_settings(user_id)

        await self.update_presence(presence, settings=settings)
        await self.subscribe_all()
        await self.dispatch_ready(settings=settings)

    async def handle_3(self, payload: Dict[str, Any]):
        """Handle OP 3 Status Update."""
        presence = payload["d"] or {}
        await self.update_presence(presence)

    async def _vsu_get_prop(self, state, data):
        """Get voice state properties from data, fallbacking to
        user settings."""
        try:
            # TODO: fetch from settings if not provided
            self_deaf = bool(data["self_deaf"])
            self_mute = bool(data["self_mute"])
        except (KeyError, ValueError):
            pass

        return {
            "deaf": state.deaf,
            "mute": state.mute,
            "self_deaf": self_deaf,
            "self_mute": self_mute,
        }

    async def handle_4(self, payload: Dict[str, Any]):
        """Handle OP 4 Voice Status Update."""
        data = payload["d"]

        if not self.state:
            return

        channel_id = int_(data.get("channel_id"))
        guild_id = int_(data.get("guild_id"))

        # TODO: none of this works, so dummy dispatches baby
        member = await self.storage.get_member(guild_id, self.state.user_id)
        update = (
            "VOICE_STATE_UPDATE",
            {
                "channel_id": str(channel_id) if channel_id else None,
                "deaf": member["deaf"] if member else False,
                "guild_id": str(guild_id) if guild_id else None,
                "member": member,
                "mute": member["mute"] if member else False,
                "request_to_speak_timestamp": None,
                "self_deaf": data.get("self_deaf", False),
                "self_mute": data.get("self_mute", False),
                "self_video": data.get("self_video", False),
                "session_id": self.state.session_id,
                "suppress": False,
                "user_id": str(self.state.user_id),
            },
        )
        if guild_id:
            await self.app.dispatcher.guild.dispatch(guild_id, update)
        elif channel_id:
            await self.app.dispatcher.channel.dispatch(channel_id, update)
        else:
            await self.dispatch_raw(*update)

        # await self.dispatch_raw(
        #     "VOICE_SERVER_UPDATE",
        #     {
        #         "endpoint": "voice.discord.media:443",
        #         "guild_id": str(guild_id) if guild_id else None,
        #         "token": "balls",
        #     }
        # )

        # if its null and null, disconnect the user from any voice
        # TODO: maybe just leave from DMs? idk...
        if channel_id is None and guild_id is None:
            return await self.app.voice.leave_all(self.state.user_id)

        # if guild is not none but channel is, we are leaving
        # a guild's channel
        if channel_id is None:
            return await self.app.voice.leave(guild_id, self.state.user_id)

        # fetch an existing state given user and guild OR user and channel
        chan_type = ChannelType(await self.storage.get_chan_type(channel_id))

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
        #
        # TODO voice_key should have a type as a 0th element to prevent
        # code from having to call get_guild(id2).
        voice_key = (self.state.user_id, state_id2)
        voice_state = await self.app.voice.get_state(voice_key)

        if voice_state is None:
            return await self.app.voice.create_state(voice_key, data)

        same_guild = guild_id == voice_state.guild_id
        same_channel = channel_id == voice_state.channel_id

        prop = await self._vsu_get_prop(voice_state, data)

        if same_guild and same_channel:
            return await self.app.voice.update_state(voice_state, prop)

        if same_guild and not same_channel:
            return await self.app.voice.move_state(voice_state, channel_id)

        # TODO: this is an edge case. we're trying to move guilds in
        # a single message, perhaps?
        log.warning("vsu payload does not appear logical")

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
            self.app.state_manager.remove(self.state.user_id)

    async def _resume(self, replay_seqs: Iterable):
        assert self.state is not None
        presences: List[dict] = []

        try:
            for seq in replay_seqs:
                try:
                    payload = self.state.store[seq]
                except KeyError:
                    # ignore unknown seqs
                    continue

                payload_t = payload.get("t")

                # presence resumption happens
                # on a separate event, PRESENCE_REPLACE.
                if payload_t == "PRESENCE_UPDATE":
                    presences.append(payload.get("d"))
                    continue

                await self.send(payload)
        except Exception:
            log.exception("error while resuming")
            await self.invalidate_session(False)
            return

        if presences:
            await self.dispatch_raw("PRESENCE_REPLACE", presences)
            await self.dispatch_raw("PRESENCES_REPLACE", presences)

        await self.dispatch_raw("RESUMED", {"_trace": ["litecord"]})

    async def handle_6(self, payload: Dict[str, Any]):
        """Handle OP 6 Resume."""
        payload = validate(payload, RESUME_SCHEMA)
        data = payload["d"]

        if data["seq"] is None:
            return await self.invalidate_session(False)

        token, sess_id, seq = data["token"], data["session_id"], data["seq"]

        try:
            user_id = await raw_token_check(token, self.app.db)
        except (Unauthorized, Forbidden):
            raise WebsocketClose(4004, "Invalid token.")

        try:
            state = self.app.state_manager.fetch(user_id, sess_id)
        except KeyError:
            return await self.invalidate_session(False)

        if seq > state.seq:
            raise WebsocketClose(4007, "Invalid sequence.")

        # check if a websocket isnt on that state already
        if state.ws is not None:
            log.info("Resuming failed, websocket already connected")
            return await self.invalidate_session(False)

        # relink this connection
        self.app.state_manager.unschedule_deletion(state)
        self.state = state
        state.ws = self

        await self._resume(range(seq, state.seq))

    async def _req_guild_members(
        self, guild_id, user_ids: List[int], query: str, limit: int, presences: bool
    ):
        try:
            guild_id = int(guild_id)
        except (TypeError, ValueError):
            log.warning("req guild members: {!r} is not an int", guild_id)
            return

        limit = limit or 1000
        exists = await self.storage.get_guild(guild_id)

        if not exists:
            log.warning("req guild members: {!r} is not a guild", guild_id)
            return

        # limit user_ids to 1000 possible members, and try your best
        # to convert them to ints, giving the same user id if it fails.
        # this is checked later on to fill the not_found array
        user_ids = [maybe_int(uid) for uid in user_ids[:1000]]

        # ASSUMPTION: requesting user_ids means we don't do query.
        if user_ids:
            log.debug(
                "req guild members: getting {} users in gid {}", len(user_ids), guild_id
            )
            members = await self.storage.get_member_multi(guild_id, user_ids)
            mids = [int(m["user"]["id"]) for m in members]

            not_found = [str(uid) for uid in user_ids if uid not in mids]
            body = {
                "guild_id": str(guild_id),
                "members": members,
                "not_found": not_found,
                "chunk_index": 0,
                "chunk_count": 1,
            }
        else:
            members = await self.storage.query_members(guild_id, query, limit)
            body = {
                "guild_id": str(guild_id),
                "members": members,
                "chunk_index": 0,
                "chunk_count": 1,
            }

        if presences:
            presences = await self.presence.guild_presences({int(m["user"]["id"]): m for m in members}, guild_id)
            body["presences"] = presences

        await self.dispatch_raw("GUILD_MEMBERS_CHUNK", body)

    async def handle_8(self, payload: Dict):
        """Handle OP 8 Request Guild Members."""

        # we do not validate guild ids because it can either be a string
        # or a list of strings and cerberus does not validate that.
        payload_copy_data = dict(payload["d"])
        payload_copy_data.pop("guild_id")
        validate({"op": 8, "d": payload_copy_data}, REQ_GUILD_SCHEMA)

        data = payload["d"]
        gids = data.get("guild_id")
        if gids is None:
            log.warning("req guilds: invalid payload: no guild id")
            return

        uids, query, limit, presences = (
            data.get("user_ids", []),
            data.get("query", ""),
            data.get("limit", 0),
            data.get("presences", False),
        )

        if isinstance(gids, (str, int)):
            await self._req_guild_members(gids, uids, query, limit, presences)
            return

        for gid in gids:
            await self._req_guild_members(gid, uids, query, limit, presences)

    async def _guild_sync(self, guild_id: int):
        """Synchronize a guild.

        Fetches the members and presences of a guild and dispatches a
        GUILD_SYNC event with that info.
        """
        members = await self.storage.get_members(guild_id)

        log.debug(f"Syncing guild {guild_id} with {len(members)} members")
        presences = await self.presence.guild_presences(members, guild_id)

        await self.dispatch_raw(
            "GUILD_SYNC",
            {
                "id": str(guild_id),
                "presences": presences,
                "members": list(members.values()),
            },
        )

    async def handle_12(self, payload: Dict[str, Any]):
        """Handle OP 12 Guild Sync."""
        payload = validate(payload, GUILD_SYNC_SCHEMA)
        data = payload["d"]
        gids = await self.user_storage.get_user_guilds(self.state.user_id)

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
        assert self.state is not None
        data = payload["d"]

        gids = await self.user_storage.get_user_guilds(self.state.user_id)
        guild_id = int(data["guild_id"])

        # make sure to not extract info you shouldn't get
        if guild_id not in gids:
            return

        log.debug("lazy request: members: {}", data.get("members", []))

        # make shard query
        for chan_id, ranges in data.get("channels", {}).items():
            chan_id = int(chan_id)

            # we need to check if the channel exists
            # or else bad things can happen
            chan_type = await app.db.fetchval(
                """
                SELECT channel_type
                FROM channels
                WHERE id = $1
                """,
                chan_id,
            )
            if chan_type is None:
                continue

            member_list = await app.lazy_guild.get_gml(chan_id)

            perms = await get_permissions(
                self.state.user_id, chan_id, storage=self.storage
            )

            if not perms.bits.read_messages:
                # ignore requests to unknown channels
                return

            await member_list.shard_query(self.state.session_id, ranges)

    async def handle_23(self, payload):
        # TODO reverse-engineer opcode 23, sent by client
        pass

    async def handle_24(self, payload):
        """OP 24 Guild Application Commands Request"""
        data = payload["d"]

        # stubbed
        await self.dispatch_raw(
            "GUILD_APPLICATION_COMMANDS_UPDATE",
            {
                "updated_at": 1630271377245,
                "nonce": data["nonce"],
                "guild_id": data["guild_id"],
                "applications": [],
                "application_commands": [],
            },
        )

    async def _process_message(self, payload):
        """Process a single message coming in from the client."""
        try:
            op_code = payload["op"]
        except KeyError:
            raise UnknownOPCode("Bad payload.")

        try:
            handler = getattr(self, f"handle_{op_code}")
        except AttributeError:
            log.warning("Payload with bad op: {}", pprint.pformat(payload))
            raise UnknownOPCode(f"Unknown OP code.")

        await handler(payload)

    async def _msg_ratelimit(self):
        if self._check_ratelimit("messages", self.state.session_id):
            raise WebsocketClose(4008, "You are being rate limited.")

    async def _listen_messages(self):
        """Listen for messages coming in from the websocket."""

        # close anyone trying to login while the
        # server is shutting down
        if self.app.state_manager.closed:
            raise GatewayError("State manager closed.")

        if not self.app.state_manager.accept_new:
            raise GatewayError("State manager not accepting logins.")

        while True:
            message = await self.ws.recv()
            if len(message) > 4096:
                raise WebsocketClose(4009, "Maximum payload length exceeded.")

            if self.state:
                await self._msg_ratelimit()

            payload = self.decoder(message)
            log.debug("received\n{}", pprint.pformat(payload))
            await self._process_message(payload)

    def _cleanup(self):
        """Cleanup any leftover tasks, and remove the connection from the
        state manager."""
        for task in self.ws_properties.tasks.values():
            task.cancel()

        if self.state:
            self.state.ws = None
            self.app.state_manager.schedule_deletion(self.state)
            self.state = None

    async def _check_conns(self, user_id):
        """Check if there are any existing connections.

        If there aren't, dispatch a presence for offline.
        """
        if not user_id:
            return

        # TODO: account for sharding. this only checks to dispatch an offline
        # when all the shards have come fully offline, which is inefficient.

        # TODO why is this inneficient?
        states = self.app.state_manager.user_states(user_id)
        if not any(s.ws for s in states):
            await self.app.presence.dispatch_pres(
                user_id, BasePresence(status="offline")
            )

    async def run(self):
        """Wrap :meth:`listen_messages` inside
        a try/except block for WebsocketClose handling."""
        try:
            async with self.app.app_context():
                await self._send_hello()
                await self._listen_messages()
        except websockets.exceptions.ConnectionClosed as err:
            log.warning("conn close, state={}, err={}", self.state, err)
        except WebsocketClose as err:
            log.warning("ws close, state={} err={}", self.state, err)
            await self.ws.close(code=err.code, reason=err.reason)
        except Exception as err:
            log.exception("An exception has occoured. state={}", self.state)
            await self.ws.close(code=4000, reason=repr(err))
        finally:
            user_id = self.state.user_id if self.state else None
            self._cleanup()
            await self._check_conns(user_id)
