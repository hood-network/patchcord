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

from typing import List, Tuple, TYPE_CHECKING

import asyncio
from logbook import Logger

from .dispatcher import DispatcherWithState, GatewayEvent
from litecord.gateway.state import GatewayState
from litecord.enums import EVENTS_TO_INTENTS, Intents
from litecord.permissions import get_permissions

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)


def can_dispatch(event_type, event_data, state) -> bool:
    if event_type == "GUILD_MEMBER_UPDATE":
        # You always get GUILD_MEMBER_UPDATE for yourself
        user_id = int(event_data["user"]["id"])
        if user_id == state.user_id:
            wanted_intent = None
        wanted_intent = Intents.GUILD_MEMBERS
    else:
        # If the return value is a tuple, it depends on `guild_id` being present
        wanted_intent = EVENTS_TO_INTENTS.get(event_type)
        if isinstance(wanted_intent, tuple):
            wanted_intent = wanted_intent[bool(event_data.get("guild_id"))]

    if wanted_intent is not None:
        return (state.intents & wanted_intent) == wanted_intent
    return True


class GuildDispatcher(DispatcherWithState[int, str, GatewayEvent, List[str]]):
    """Guild backend for Pub/Sub."""

    async def sub_user(
        self, guild_id: int, user_id: int
    ) -> Tuple[List[GatewayState], List[int]]:
        states = app.state_manager.fetch_states(user_id, guild_id)
        asyncio.gather(*(self.sub(guild_id, state.session_id) for state in states))

        # instead of calculating which channels to subscribe to
        # inside guild dispatcher, we calculate them in here, so that
        # we remove complexity of the dispatcher.

        guild_chan_ids = await app.storage.get_channel_ids(guild_id)
        channel_ids = []
        async def sub_channel(channel_id):
            perms = await get_permissions(user_id, channel_id)
            if perms.bits.read_messages:
                channel_ids.append(channel_id)
        await asyncio.gather(*(sub_channel(chan_id) for chan_id in guild_chan_ids))

        return states, channel_ids

    async def unsub_user(
        self, guild_id: int, user_id: int
    ) -> Tuple[List[GatewayState], List[int]]:
        states = app.state_manager.fetch_states(user_id, guild_id)
        asyncio.gather(*(self.unsub(guild_id, state.session_id) for state in states))
        guild_chan_ids = await app.storage.get_channel_ids(guild_id)
        return states, guild_chan_ids

    async def dispatch_filter(
        self, guild_id: int, filter_function, event: GatewayEvent
    ):
        session_ids = self.state[guild_id]
        sessions: List[str] = []
        event_type, event_data = event

        async def _dispatch(session_id: str) -> None:
            if filter_function and not filter_function(session_id):
                return

            try:
                state = app.state_manager.fetch_raw(session_id)
            except KeyError:
                await self.unsub(guild_id, session_id)
                return

            if not state:
                await self.unsub(guild_id, session_id)
                return

            if not can_dispatch(event_type, event_data, state):
                return

            try:
                await state.dispatch(*event)
            except Exception:
                log.exception("error while dispatching to {}", state.session_id)
                return

            sessions.append(session_id)

        await asyncio.gather(*(_dispatch(sess_id) for sess_id in session_ids))
        log.info("Dispatched {} {!r} to {} states", guild_id, event[0], len(sessions))
        return sessions

    async def dispatch(self, guild_id: int, event):
        """Dispatch an event to all subscribers of the guild."""
        return await self.dispatch_filter(guild_id, None, event)
