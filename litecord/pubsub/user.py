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

from typing import Callable, List, Optional, TYPE_CHECKING

from .dispatcher import GatewayEvent
from .utils import send_event_to_states

if TYPE_CHECKING:
    from litecord.typing_hax import app
else:
    from quart import current_app as app

async def dispatch_user_filter(
    user_id: int, filter_func: Optional[Callable[[str], bool]], event_data: GatewayEvent
) -> List[str]:
    """Dispatch to a given user's states, but only for states
    where filter_func returns true."""
    states = list(
        filter(
            lambda state: filter_func(state.session_id) if filter_func else True,
            app.state_manager.user_states(user_id),
        )
    )

    return await send_event_to_states(states, event_data)


async def dispatch_user(user_id: int, event_data: GatewayEvent) -> List[str]:
    return await dispatch_user_filter(user_id, None, event_data)
