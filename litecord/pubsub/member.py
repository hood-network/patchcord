"""

Litecord
Copyright (C) 2018  Luna Mendes

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

from .dispatcher import Dispatcher


class MemberDispatcher(Dispatcher):
    """Member backend for Pub/Sub."""
    KEY_TYPE = tuple

    async def dispatch(self, key, event, data):
        """Dispatch a single event to a member.

        This is shard-aware.
        """
        # we don't keep any state on this dispatcher, so the key
        # is just (guild_id, user_id)
        guild_id, user_id = key

        # fetch shards
        states = self.sm.fetch_states(user_id, guild_id)

        # if no states were found, we should
        # unsub the user from the GUILD channel
        if not states:
            await self.main_dispatcher.unsub('guild', guild_id, user_id)
            return

        return await self._dispatch_states(states, event, data)
