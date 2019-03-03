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

from typing import Tuple, Dict
from collections import defaultdict
from dataclasses import fields

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
        ctype = ChannelType(channel['type'])

        if ctype not in VOICE_CHANNELS:
            return

        states = await self.app.voice.state_count(channel_id)

        # get_permissions returns ALL_PERMISSIONS when
        # the channel isn't from a guild
        perms = await get_permissions(
            user_id, channel_id, storage=self.app.storage
        )

        # hacky user_limit but should work, as channels not
        # in guilds won't have that field.
        is_full = states >= channel.get('user_limit', 100)
        is_bot = (await self.app.storage.get_user(user_id))['bot']
        is_manager = perms.bits.manage_channels

        # if the channel is full AND:
        #  - user is not a bot
        #  - user is not manage channels
        # then it fails
        if not is_bot and not is_manager and is_full:
            return

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
            if field in ('channel_id', 'user_id'):
                raise ValueError('properties are updating channel or user')

            new_state_dict[field] = prop[field]

        new_state = _construct_state(new_state_dict)

        # TODO: dispatch to voice server
        self.states[state.key][state.user_id] = new_state

    async def move_channels(self, old_voice_key: VoiceKey, channel_id: int):
        """Move a user between channels."""
        await self.del_state(old_voice_key)
        await self.create_state(old_voice_key, channel_id, {})

    async def create_state(self, voice_key: VoiceKey, channel_id: int,
                           data: dict):
        pass

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
