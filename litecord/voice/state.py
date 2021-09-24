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

from dataclasses import dataclass, asdict


@dataclass
class VoiceState:
    """Represents a voice state."""

    guild_id: int
    channel_id: int
    user_id: int
    session_id: str
    deaf: bool
    mute: bool
    self_deaf: bool
    self_mute: bool
    suppressed_by: int

    @property
    def key(self):
        """Get the second part of a key identifying a state."""
        return self.channel_id if self.guild_id is None else self.guild_id

    @property
    def as_json(self):
        """Return JSON-serializable dict."""
        return asdict(self)

    def as_json_for(self, user_id: int):
        """Generate JSON-serializable version, given a user ID."""
        self_dict = asdict(self)

        if user_id is None:
            return self_dict

        # state.suppress is defined by the user
        # that is currently viewing the state.

        # a better approach would be actually using
        # the suppressed_by field for backend efficiency.
        self_dict["suppress"] = user_id == self.suppressed_by
        self_dict.pop("suppressed_by")

        return self_dict
