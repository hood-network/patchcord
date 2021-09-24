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

import hashlib
import os
from typing import Optional, Any

import websockets
from logbook import Logger

from litecord.presence import BasePresence
from litecord.enums import Intents
from .opcodes import OP

log = Logger(__name__)


def gen_session_id() -> str:
    """Generate a random session ID."""
    return hashlib.sha1(os.urandom(128)).hexdigest()


class PayloadStore:
    """Store manager for payloads.

    This will only store a maximum of MAX_STORE_SIZE,
    dropping the older payloads when adding new ones.
    """

    MAX_STORE_SIZE = 250

    def __init__(self):
        self.store = {}

    def __getitem__(self, opcode: int):
        return self.store[opcode]

    def __setitem__(self, opcode: int, payload: dict):
        if len(self.store) > 250:
            # if more than 250, remove old keys until we get 250
            opcodes = sorted(list(self.store.keys()))
            to_remove = len(opcodes) - self.MAX_STORE_SIZE

            for idx in range(to_remove):
                opcode = opcodes[idx]
                self.store.pop(opcode)

        self.store[opcode] = payload


class GatewayState:
    """Main websocket state.

    Used to store all information tied to the websocket's session.
    """

    def __init__(self, **kwargs):
        self.session_id: str = kwargs.get("session_id", gen_session_id())

        #: last seq received by the client
        self.seq: int = int(kwargs.get("seq") or 0)

        #: last seq sent by gateway
        self.last_seq: int = 0

        #: shard information (id and total count)
        shard = kwargs.get("shard") or [0, 1]
        self.current_shard: int = int(shard[0])
        self.shard_count: int = int(shard[1])

        self.user_id: int = int(kwargs["user_id"])
        self.bot: bool = bool(kwargs.get("bot") or False)

        #: set by the gateway connection
        #  on OP STATUS_UPDATE
        self.presence: Optional[BasePresence] = None

        #: set by the backend once identify happens
        self.ws = None

        #: store of all payloads sent by the gateway (for recovery purposes)
        self.store = PayloadStore()

        self.compress: bool = kwargs.get("compress") or False

        self.large: int = kwargs.get("large") or 50
        self.intents: Intents = kwargs["intents"]

    def __bool__(self):
        """Return if the given state is a valid state to be used."""
        return self.ws is not None

    def __repr__(self):
        return f"GatewayState<seq={self.seq} shard={self.current_shard},{self.shard_count} uid={self.user_id}>"

    async def dispatch(self, event_type: str, event_data: Any) -> None:
        """Dispatch an event to the underlying websocket.

        Stores the event in the state's payload store for resuming.
        """
        self.seq += 1
        payload = {
            "op": OP.DISPATCH,
            "t": event_type.upper(),
            "s": self.seq,
            "d": event_data,
        }

        self.store[self.seq] = payload

        log.debug("dispatching event {!r} to session {}", payload["t"], self.session_id)

        try:
            if self.ws:
                # replies compat on v8+
                if (
                    event_type.startswith("MESSAGE_")
                    and (payload.get("d") or {}).get("message_reference") is not None
                    and self.ws.ws_properties.version > 7
                ):
                    payload["d"]["type"] = 19

                # guild delete compat on v7(?)+
                if (
                    event_type == "GUILD_DELETE"
                    and (payload.get("d") or {}).get("guild_id") is not None
                    and self.ws.ws_properties.version > 6
                ):
                    payload["d"]["id"] = payload["d"]["guild_id"]
                    payload["d"].pop("guild_id")

                await self.ws.send(payload)
        except websockets.exceptions.ConnectionClosed as exc:
            log.warning(
                "Failed to dispatch {!r} to session id {}: {!r}",
                payload["t"],
                self.session_id,
                exc,
            )
