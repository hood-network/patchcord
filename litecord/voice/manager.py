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

from typing import Tuple, Dict, List
from collections import defaultdict
from dataclasses import fields
from quart import current_app as app

from logbook import Logger

from litecord.permissions import get_permissions
from litecord.enums import ChannelType, VOICE_CHANNELS
from litecord.voice.state import VoiceState
from litecord.voice.lvsp_manager import LVSPManager


VoiceKey = Tuple[int, int]
log = Logger(__name__)


def _construct_state(state_dict: dict) -> VoiceState:
    """Create a VoiceState instance out of a dictionary with the
    VoiceState fields as keys."""
    state_fields = fields(VoiceState)
    args = [state_dict[field.name] for field in state_fields]
    return VoiceState(*args)


class VoiceManager:
    """Main voice manager class."""

    def __init__(self, app):
        self.app = app

        # double dict, first key is guild/channel id, second key is user id
        self.states = defaultdict(dict)
        self.lvsp = LVSPManager(app, self)

        # TODO: map channel ids to voice servers

    async def can_join(self, user_id: int, channel_id: int) -> int:
        """Return if a user can join a channel."""

        channel = await self.app.storage.get_channel(channel_id)
        ctype = ChannelType(channel["type"])

        if ctype not in VOICE_CHANNELS:
            return False

        states = await self.app.voice.state_count(channel_id)

        # get_permissions returns ALL_PERMISSIONS when
        # the channel isn't from a guild
        perms = await get_permissions(user_id, channel_id, storage=self.app.storage)

        # hacky user_limit but should work, as channels not
        # in guilds won't have that field.
        is_full = states >= channel.get("user_limit", 100)
        is_bot = (await self.app.storage.get_user(user_id))["bot"]
        is_manager = perms.bits.manage_channels

        # if the channel is full AND:
        #  - user is not a bot
        #  - user is not manage channels
        # then it fails
        if not is_bot and not is_manager and is_full:
            return False

        # all good
        return True

    async def state_count(self, channel_id: int) -> int:
        """Get the current amount of voice states in a channel."""
        return len(self.states[channel_id])

    async def fetch_states(self, channel_id: int) -> Dict[int, VoiceState]:
        """Fetch the states of the given channel."""
        # since the state key is (user_id, guild_id | channel_id), we need
        # to determine which kind of search we want to do.
        guild_id = await self.app.storage.guild_from_channel(channel_id)

        # if there isn't a guild for the channel, it is a dm or group dm.
        # those are simple to handle.
        if not guild_id:
            return dict(self.states[channel_id])

        # guild states hold a dict mapping user ids to guild states,
        # same as channels, thats the structure.
        guild_states = self.states[guild_id]
        res = {}

        # iterate over all users with states and add the channel matches
        # into res
        for user_id, state in guild_states.items():
            if state.channel_id == channel_id:
                res[user_id] = state

        return res

    async def get_state(self, voice_key: VoiceKey) -> VoiceState:
        """Get a single VoiceState for a user in a channel. Returns None
        if no VoiceState is found."""
        user_id, sec_key_id = voice_key

        try:
            return self.states[sec_key_id][user_id]
        except KeyError:
            return None

    async def del_state(self, voice_key: VoiceKey):
        """Delete a given voice state."""
        user_id, sec_key_id = voice_key

        try:
            # TODO: tell that to the voice server of the channel.
            self.states[sec_key_id].pop(user_id)
        except KeyError:
            pass

    async def update_state(self, state: VoiceState, prop: dict):
        """Update a state in a channel"""
        # construct a new state based on the old one + properties
        new_state_dict = dict(state.as_json)

        for field in prop:
            # NOTE: this should not happen, ever.
            if field in ("channel_id", "user_id"):
                raise ValueError("properties are updating channel or user")

            new_state_dict[field] = prop[field]

        new_state = _construct_state(new_state_dict)

        # TODO: dispatch to voice server
        self.states[state.key][state.user_id] = new_state

    async def move_channels(self, old_voice_key: VoiceKey, channel_id: int):
        """Move a user between channels."""
        await self.del_state(old_voice_key)
        await self.create_state(old_voice_key, {"channel_id": channel_id})

    async def _lvsp_info_guild(self, guild_id, info_type, info_data):
        hostname = await self.lvsp.get_guild_server(guild_id)
        if hostname is None:
            log.error("no voice server for guild id {}", guild_id)
            return

        conn = self.lvsp.get_conn(hostname)
        if conn is None:
            log.error("not connected to server {!r}", hostname)
            return

        await conn.send_info(info_type, info_data)

    async def _create_ctx_guild(self, guild_id, channel_id):
        await self._lvsp_info_guild(
            guild_id,
            "CHANNEL_REQ",
            {"guild_id": str(guild_id), "channel_id": str(channel_id)},
        )

    async def _start_voice_guild(self, voice_key: VoiceKey, data: dict):
        """Start a voice context in a guild."""
        user_id, guild_id = voice_key
        channel_id = int(data["channel_id"])

        existing_states = self.states[voice_key]
        channel_exists = any(
            state.channel_id == channel_id for state in existing_states
        )

        if not channel_exists:
            await self._create_ctx_guild(guild_id, channel_id)

        await self._lvsp_info_guild(
            guild_id,
            "VST_CREATE",
            {
                "user_id": str(user_id),
                "guild_id": str(guild_id),
                "channel_id": str(channel_id),
            },
        )

    async def create_state(self, voice_key: VoiceKey, data: dict):
        """Creates (or tries to create) a voice state.

        Depending on the VoiceKey given, it will use the guild's voice
        region or assign one based on the starter of a call, or the owner of
        a Group DM.

        Once a region is assigned, it'll choose the best voice server
        and send a request to it.
        """

        # TODO: handle CALL events.

        # compare if this voice key is for a guild or a channel
        _uid, id2 = voice_key
        guild = await self.app.storage.get_guild(id2)

        # if guild not found, then we are dealing with a dm or group dm
        if not guild:
            ctype = await self.app.storage.get_chan_type(id2)
            ctype = ChannelType(ctype)

            if ctype == ChannelType.GROUP_DM:
                # await self._start_voice_dm(voice_key)
                pass
            elif ctype == ChannelType.DM:
                # await self._start_voice_gdm(voice_key)
                pass

            return

        # if guild found, then data.channel_id exists, and we treat it
        # as a guild
        await self._start_voice_guild(voice_key, data)

    async def leave_all(self, user_id: int) -> int:
        """Leave all voice channels."""

        # iterate over every state finding matches

        # NOTE: we copy the current states dict since we're modifying
        # on iteration. this is SLOW.

        # TODO: better solution instead of copying, maybe we can generate
        # a list of tasks to run that actually do the deletion by themselves
        # instead of us generating a delete. then only start running them later
        # on.
        for sec_key_id, states in dict(self.states).items():
            for state in states:
                if state.user_id != user_id:
                    continue

                await self.del_state((user_id, sec_key_id))

    async def leave(self, guild_id: int, user_id: int):
        """Make a user leave a channel IN A GUILD."""
        await self.del_state((guild_id, user_id))

    async def voice_server_list(self, region: str) -> List[dict]:
        """Get a list of voice server objects"""
        rows = await self.app.db.fetch(
            """
        SELECT hostname, last_health
        FROM voice_servers
        WHERE region_id = $1
        """,
            region,
        )

        return list(map(dict, rows))

    async def disable_region(self, region: str) -> None:
        """Disable a region."""
        guild_ids = await self.app.db.fetch(
            """
            UPDATE guilds
            SET region = null
            WHERE region = $1
            RETURNING guild_id
            """,
            region,
        )

        guild_count = len(guild_ids)
        log.info("updated {} guilds. region={} to null", guild_count, region)

        # slow, but it be like that, also copied from other users...
        for guild_id in guild_ids:
            guild = await self.app.storage.get_guild_full(guild_id, None)
            await app.dispatcher.guild.dispatch(guild_id, ("GUILD_UPDATE", guild))

        # TODO propagate the channel deprecation to LVSP connections
