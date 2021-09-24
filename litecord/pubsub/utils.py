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

import logging
from typing import List, Tuple, Any
from ..gateway.state import GatewayState

log = logging.getLogger(__name__)


async def send_event_to_states(
    states: List[GatewayState], event_data: Tuple[str, Any]
) -> List[str]:
    """Dispatch an event to a list of states."""
    res = []

    event, data = event_data
    for state in states:
        try:
            await state.dispatch(event, data)
            res.append(state.session_id)
        except Exception:
            log.exception("error while dispatching")

    return res
