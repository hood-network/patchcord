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

from typing import List

from quart import current_app as app
from logbook import Logger

from .dispatcher import DispatcherWithState, GatewayEvent
from litecord.gateway.state import GatewayState
from litecord.enums import EVENTS_TO_INTENTS

log = Logger(__name__)


def can_dispatch(event_type, event_data, state) -> bool:
    # If we're sending to the same user for this kind of event,
    # bypass event logic (always send)
    if event_type == "GUILD_MEMBER_UPDATE":
        user_id = int(event_data["user"]["id"])
        return user_id == state.user_id

    # TODO Guild Create and Req Guild Members have specific
    # logic regarding the presence intent.

    wanted_intent = EVENTS_TO_INTENTS.get(event_type)
    if wanted_intent is not None:
        state_has_intent = (state.intents & wanted_intent) == wanted_intent
        return state_has_intent


class GuildDispatcher(DispatcherWithState[int, str, GatewayEvent, List[str]]):
    """Guild backend for Pub/Sub."""

    async def sub_user(self, guild_id: int, user_id: int) -> List[GatewayState]:
        states = app.state_manager.fetch_states(user_id, guild_id)
        for state in states:
            await self.sub(guild_id, state.session_id)

        return states

    async def dispatch_filter(
        self, guild_id: int, filter_function, event: GatewayEvent
    ):
        session_ids = self.state[guild_id]
        sessions: List[str] = []
        event_type, event_data = event

        for session_id in set(session_ids):
            if not filter_function(session_id):
                continue

            try:
                state = app.state_manager.fetch_raw(session_id)
            except KeyError:
                await self.unsub(guild_id, session_id)
                continue

            if not state:
                await self.unsub(guild_id, session_id)
                continue

            if not can_dispatch(event_type, event_data, state):
                continue

            try:
                await state.ws.dispatch(*event)
            except Exception:
                log.exception("error while dispatching to {}", state.session_id)
                continue

            sessions.append(session_id)

        log.info("Dispatched {} {!r} to {} states", guild_id, event[0], len(sessions))
        return sessions

    async def dispatch(self, guild_id: int, event):
        """Dispatch an event to all subscribers of the guild."""
        return await self.dispatch_filter(guild_id, lambda sess_id: True, event)
