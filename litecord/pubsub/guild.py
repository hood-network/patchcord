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
from dataclasses import dataclass

from quart import current_app as app
from logbook import Logger

from .dispatcher import DispatcherWithFlags, GatewayEvent
from .channel import ChannelFlags
from litecord.gateway.state import GatewayState
from litecord.enums import Intents

log = Logger(__name__)


@dataclass
class GuildFlags(ChannelFlags):
    presence: bool


EVENTS_TO_INTENTS = {
    "GUILD_CREATE": Intents.GUILDS,
    "GUILD_UPDATE": Intents.GUILDS,
    "GUILD_DELETE": Intents.GUILDS,
    "GUILD_ROLE_CREATE": Intents.GUILDS,
    "GUILD_ROLE_UPDATE": Intents.GUILDS,
    "GUILD_ROLE_DELETE": Intents.GUILDS,
    "CHANNEL_CREATE": Intents.GUILDS,
    "CHANNEL_UPDATE": Intents.GUILDS,
    "CHANNEL_DELETE": Intents.GUILDS,
    "CHANNEL_PINS_UPDATE": Intents.GUILDS,
    # --- threads not supported --
    "THREAD_CREATE": Intents.GUILDS,
    "THREAD_UPDATE": Intents.GUILDS,
    "THREAD_DELETE": Intents.GUILDS,
    "THREAD_LIST_SYNC": Intents.GUILDS,
    "THREAD_MEMBER_UPDATE": Intents.GUILDS,
    "THREAD_MEMBERS_UPDATE": Intents.GUILDS,
    # --- stages not supported --
    "STAGE_INSTANCE_CREATE": Intents.GUILDS,
    "STAGE_INSTANCE_UPDATE": Intents.GUILDS,
    "STAGE_INSTANCE_DELETE": Intents.GUILDS,
    "GUILD_MEMBER_ADD": Intents.GUILD_MEMBERS,
    "GUILD_MEMBER_UPDATE": Intents.GUILD_MEMBERS,
    "GUILD_MEMBER_REMOVE": Intents.GUILD_MEMBERS,
    # --- threads not supported --
    "THREAD_MEMBERS_UPDATE ": Intents.GUILD_MEMBERS,
    "GUILD_BAN_ADD": Intents.GUILD_BANS,
    "GUILD_BAN_REMOVE": Intents.GUILD_BANS,
    "GUILD_EMOJIS_UPDATE": Intents.GUILD_EMOJIS,
    "GUILD_INTEGRATIONS_UPDATE": Intents.GUILD_INTEGRATIONS,
    "INTEGRATION_CREATE": Intents.GUILD_INTEGRATIONS,
    "INTEGRATION_UPDATE": Intents.GUILD_INTEGRATIONS,
    "INTEGRATION_DELETE": Intents.GUILD_INTEGRATIONS,
    "WEBHOOKS_UPDATE": Intents.GUILD_WEBHOOKS,
    "INVITE_CREATE": Intents.GUILD_INVITES,
    "INVITE_DELETE": Intents.GUILD_INVITES,
    "VOICE_STATE_UPDATE": Intents.GUILD_VOICE_STATES,
    "PRESENCE_UPDATE": Intents.GUILD_PRESENCES,
    "MESSAGE_CREATE": Intents.GUILD_MESSAGES,
    "MESSAGE_UPDATE": Intents.GUILD_MESSAGES,
    "MESSAGE_DELETE": Intents.GUILD_MESSAGES,
    "MESSAGE_DELETE_BULK": Intents.GUILD_MESSAGES,
    "MESSAGE_REACTION_ADD": Intents.GUILD_MESSAGE_REACTIONS,
    "MESSAGE_REACTION_REMOVE": Intents.GUILD_MESSAGE_REACTIONS,
    "MESSAGE_REACTION_REMOVE_ALL": Intents.GUILD_MESSAGE_REACTIONS,
    "MESSAGE_REACTION_REMOVE_EMOJI": Intents.GUILD_MESSAGE_REACTIONS,
    "TYPING_START": Intents.GUILD_MESSAGE_TYPING,
}


class GuildDispatcher(
    DispatcherWithFlags[int, str, GatewayEvent, List[str], GuildFlags]
):
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
        event_type, _ = event

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

            wanted_intent = EVENTS_TO_INTENTS[event_type]
            state_has_intent = (state.intents & wanted_intent) == wanted_intent
            if not state_has_intent:
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
