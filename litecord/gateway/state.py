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
from litecord.utils import index_by_func
from .opcodes import OP

log = Logger(__name__)


def gen_session_id() -> str:
    """Generate a random session ID."""
    return hashlib.sha1(os.urandom(128)).hexdigest()


def content_allowed(user_id: str, intents: Intents, data: dict) -> bool:
    # Message content is returned if any of the following is true:
    # - User has the message content intent
    # - The message is not from a guild
    # - The user is the message author
    # - The user is explicitly mentioned in the message
    # Otherwise, `content`, `embeds`, `attachments`, and `components` are yeeted
    return (
        (intents & Intents.MESSAGE_CONTENT == Intents.MESSAGE_CONTENT)
        or not data.get("guild_id")
        or user_id == data.get("author", {}).get("id")
        or user_id in data.get("mentions", [])
    )


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
            "d": dict(event_data) if event_data else None,
        }

        self.store[self.seq] = payload

        log.debug("dispatching event {!r} to session {}", payload["t"], self.session_id)

        try:
            if self.ws:
                # Various old API version compatibility crap
                data = payload.get("d") or {}

                if event_type in ("MESSAGE_CREATE", "MESSAGE_UPDATE"):
                    data.pop("reactions", None)
                    data["referenced_message"] = data.get("referenced_message") or None
                    if (
                        data.get("type") in (19, 20, 23)
                        and self.ws.ws_properties.version < 8
                    ):
                        data["type"] = 0

                    if not content_allowed(str(self.user_id), self.intents, data):
                        if data.get("content"):
                            data["content"] = ""
                        if data.get("embeds"):
                            data["embeds"] = []
                        if data.get("attachments"):
                            data["attachments"] = []
                        if data["referenced_message"] and not content_allowed(
                            str(self.user_id), self.intents, data["referenced_message"]
                        ):
                            data["referenced_message"].update(
                                {"content": "", "embeds": [], "attachments": []}
                            )

                elif (
                    event_type.startswith("GUILD_ROLE_")
                    and "role" in data
                    and data.get("permissions") is not None
                    and self.ws.ws_properties.version < 8
                ):
                    data["permissions_new"] = data["permissions"]
                    data["permissions"] = int(data["permissions"]) & ((2 << 31) - 1)

                elif (
                    event_type.startswith("CHANNEL_")
                ):
                    if data.get("type") == 3:
                        idx = index_by_func(lambda user: user["id"] == str(self.user_id), data["recipients"])
                        if idx is not None:
                            data["recipients"].pop(idx)

                    if data.get("permission_overwrites") and self.ws.ws_properties.version < 8:
                        for overwrite in data["permission_overwrites"]:
                            overwrite["type"] = (
                                "role" if overwrite["type"] == 0 else "member"
                            )
                            overwrite["allow_new"] = overwrite.get("allow", "0")
                            overwrite["allow"] = (
                                (int(overwrite["allow"]) & ((2 << 31) - 1))
                                if overwrite.get("allow")
                                else 0
                            )
                            overwrite["deny_new"] = overwrite.get("deny", "0")
                            overwrite["deny"] = (
                                (int(overwrite["deny"]) & ((2 << 31) - 1))
                                if overwrite.get("deny")
                                else 0
                            )

                elif (
                    event_type in ("GUILD_CREATE", "GUILD_UPDATE")
                    and self.ws.ws_properties.version < 8
                ):
                    for role in data.get("roles", []):
                        role["permissions_new"] = role["permissions"]
                        role["permissions"] = int(role["permissions"]) & ((2 << 31) - 1)
                    for channel in data.get("channels", []):
                        channel["permission_overwrites"] = [
                            {
                                "id": overwrite["id"],
                                "type": "role" if overwrite["type"] == 0 else "member",
                                "allow_new": overwrite.get("allow", "0"),
                                "allow": (int(overwrite["allow"]) & ((2 << 31) - 1))
                                if overwrite.get("allow")
                                else 0,
                                "deny_new": overwrite.get("deny", "0"),
                                "deny": (int(overwrite["deny"]) & ((2 << 31) - 1))
                                if overwrite.get("deny")
                                else 0,
                            }
                            for overwrite in channel["permission_overwrites"]
                        ]

                await self.ws.send(payload)
        except websockets.exceptions.ConnectionClosed as exc:
            log.warning(
                "Failed to dispatch {!r} to session id {}: {!r}",
                payload["t"],
                self.session_id,
                exc,
            )
