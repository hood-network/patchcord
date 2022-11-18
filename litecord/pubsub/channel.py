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

from typing import List, TYPE_CHECKING

import asyncio
from logbook import Logger

from litecord.enums import EVENTS_TO_INTENTS
from .dispatcher import DispatcherWithState, GatewayEvent

if TYPE_CHECKING:
    from litecord.typing_hax import app
else:
    from quart import current_app as app
    
log = Logger(__name__)


def can_dispatch(event_type, event_data, state) -> bool:
    # If the return value is a tuple, it depends on `guild_id` being present
    wanted_intent = EVENTS_TO_INTENTS.get(event_type)
    if isinstance(wanted_intent, tuple):
        wanted_intent = wanted_intent[bool(event_data.get("guild_id"))]

    if wanted_intent is not None:
        return (state.intents & wanted_intent) == wanted_intent
    return True


class ChannelDispatcher(DispatcherWithState[int, str, GatewayEvent, List[str]]):
    """Main channel Pub/Sub logic. Handles both Guild, DM, and Group DM channels."""

    async def dispatch(self, channel_id: int, event: GatewayEvent) -> List[str]:
        """Dispatch an event to a channel."""
        session_ids = set(self.state[channel_id])
        sessions: List[str] = []

        event_type, event_data = event

        async def _dispatch(session_id: str) -> None:
            try:
                state = app.state_manager.fetch_raw(session_id)
            except KeyError:
                await self.unsub(channel_id, session_id)
                return

            if not can_dispatch(event_type, event_data, state):
                return

            await state.dispatch(*event)
            sessions.append(session_id)

        await asyncio.gather(*(_dispatch(sid) for sid in session_ids))

        log.info(
            "Dispatched chan={} {!r} to {} states", channel_id, event[0], len(sessions)
        )

        return sessions
