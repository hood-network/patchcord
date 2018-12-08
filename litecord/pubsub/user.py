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


class UserDispatcher(Dispatcher):
    """User backend for Pub/Sub."""
    KEY_TYPE = int

    async def dispatch_filter(self, user_id: int, func, event, data):
        """Dispatch an event to all shards of a user."""

        # filter only states where func() gives true
        states = list(filter(
            lambda state: func(state.session_id),
            self.sm.user_states(user_id)
        ))

        return await self._dispatch_states(states, event, data)

    async def dispatch(self, user_id: int, event, data):
        return await self.dispatch_filter(
            user_id,
            lambda sess_id: True,
            event, data,
        )
