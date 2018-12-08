"""

Litecord
Copyright (C) 2018  Luna Mendes

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
        self.session_id = kwargs.get('session_id', gen_session_id())

        #: event sequence number
        self.seq = kwargs.get('seq', 0)

        #: last seq sent by us, the backend
        self.last_seq = 0

        #: shard information about the state,
        #  its id and shard count
        self.shard = kwargs.get('shard', [0, 1])

        self.user_id = kwargs.get('user_id')
        self.bot = kwargs.get('bot', False)

        #: set by the gateway connection
        #  on OP STATUS_UPDATE
        self.presence = {}

        #: set by the backend once identify happens
        self.ws = None

        #: store (kind of) all payloads sent by us
        self.store = PayloadStore()

        for key in kwargs:
            value = kwargs[key]
            self.__dict__[key] = value

    def __repr__(self):
        return (f'GatewayState<seq={self.seq} '
                f'shard={self.shard} uid={self.user_id}>')
