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

from typing import List

from quart import current_app as app
from logbook import Logger

from litecord.enums import ChannelType, EVENTS_TO_INTENTS
from litecord.utils import index_by_func
from .dispatcher import DispatcherWithState, GatewayEvent

log = Logger(__name__)


def gdm_recipient_view(orig: dict, user_id: int) -> dict:
    """Create a copy of the original channel object that doesn't
    show the user we are dispatching it to.

    this only applies to group dms and discords' api design that says
    a group dms' recipients must not show the original user.
    """
    # make a copy or the original channel object
    data = dict(orig)
    idx = index_by_func(lambda user: user["id"] == str(user_id), data["recipients"])
    data["recipients"].pop(idx)
    return data


class ChannelDispatcher(DispatcherWithState[int, str, GatewayEvent, List[str]]):
    """Main channel Pub/Sub logic. Handles both Guild, DM, and Group DM channels."""

    async def dispatch(self, channel_id: int, event: GatewayEvent) -> List[str]:
        """Dispatch an event to a channel."""
        session_ids = set(self.state[channel_id])
        sessions: List[str] = []

        event_type, event_data = event
        assert isinstance(event_data, dict)

        for session_id in session_ids:
            try:
                state = app.state_manager.fetch_raw(session_id)
            except KeyError:
                await self.unsub(channel_id, session_id)
                continue

            wanted_intent = EVENTS_TO_INTENTS.get(event_type)
            if wanted_intent is not None:
                state_has_intent = (state.intents & wanted_intent) == wanted_intent
                if not state_has_intent:
                    continue

            correct_event = event
            # for cases where we are talking about group dms, we create an edited
            # event data so that it doesn't show the user we're dispatching
            # to in data.recipients (clients already assume they are recipients)
            if (
                event_type in ("CHANNEL_CREATE", "CHANNEL_UPDATE")
                and event_data.get("type") == ChannelType.GROUP_DM.value
            ):
                new_data = gdm_recipient_view(event_data, state.user_id)
                correct_event = (event_type, new_data)

            await state.dispatch(*correct_event)
            sessions.append(session_id)

        log.info(
            "Dispatched chan={} {!r} to {} states", channel_id, event[0], len(sessions)
        )

        return sessions
