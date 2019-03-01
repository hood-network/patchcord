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

from typing import Tuple
from collections import defaultdict
from dataclasses import fields

from logbook import Logger

from litecord.voice.state import VoiceState


VoiceKey = Tuple[int, int]
log = Logger(__name__)


def _construct_state(state_dict: dict) -> VoiceState:
    """Create a VoiceState instance out of a dictionary with the
    VoiceState fields as keys."""
    fields = fields(VoiceState)
    args = [state_dict[field.name] for field in fields]
    return VoiceState(*args)


class VoiceManager:
    """Main voice manager class."""
    def __init__(self, app):
        self.app = app

        self.states = defaultdict(dict)

        # TODO: hold voice server LVSP connections
        # TODO: map channel ids to voice servers

    async def state_count(self, channel_id: int) -> int:
        """Get the current amount of voice states in a channel."""
        return len(self.states[channel_id])

    async def del_state(self, voice_key: VoiceKey):
        """Delete a given voice state."""
        chan_id, user_id = voice_key

        try:
            # TODO: tell that to the voice server of the channel.
            self.states[chan_id].pop(user_id)
        except KeyError:
            pass

    async def update_state(self, voice_key: VoiceKey, prop: dict):
        """Update a state in a channel"""
        chan_id, user_id = voice_key

        try:
            state = self.states[chan_id][user_id]
        except KeyError:
            return

        # construct a new state based on the old one + properties
        new_state_dict = dict(state.as_json)

        for field in prop:
            # NOTE: this should not happen, ever.
            if field in ('channel_id', 'user_id'):
                raise ValueError('properties are updating channel or user')

            new_state_dict[field] = prop[field]

        new_state = _construct_state(new_state_dict)

        # TODO: dispatch to voice server
        self.states[chan_id][user_id] = new_state

    async def move_channels(self, old_voice_key: VoiceKey, channel_id: int):
        """Move a user between channels."""
        await self.del_state(old_voice_key)
        await self.create_state(old_voice_key, channel_id, {})

    async def create_state(self, voice_key: VoiceKey, channel_id: int,
                           data: dict):
        pass
