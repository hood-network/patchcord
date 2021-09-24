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


class GuildMemoryStore:
    """Store in-memory properties about guilds.

    I could have just used Redis... probably too overkill to add
    aioredis to the already long depedency list, plus, I don't need
    """

    def __init__(self):
        self._store = {}

    def get(self, guild_id: int, attribute: str, default=None):
        """get a key"""
        return self._store.get(f"{guild_id}:{attribute}", default)

    def set(self, guild_id: int, attribute: str, value):
        """set a key"""
        self._store[f"{guild_id}:{attribute}"] = value
