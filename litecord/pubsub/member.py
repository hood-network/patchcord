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
from .dispatcher import GatewayEvent
from .utils import send_event_to_states

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

async def dispatch_member(
    guild_id: int, user_id: int, event: GatewayEvent
) -> List[str]:
    states = app.state_manager.fetch_states(user_id, guild_id)

    # if no states were found, we should unsub the user from the guild
    if not states:
        await app.dispatcher.guild.unsub(guild_id, user_id)
        return []

    return await send_event_to_states(states, event)
