import hashlib
import os


def gen_session_id() -> str:
    """Generate a random session ID."""
    return hashlib.sha1(os.urandom(128)).hexdigest()


class PayloadStore:
    """Store manager for payloads."""
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


class Presence:
    def __init__(self, raw: dict):
        self.afk = raw.get('afk', False)
        self.status = raw.get('status', 'online')
        self.game = raw.get('game', None)
        self.since = raw.get('since', 0)


class GatewayState:
    """Main websocket state.

    Used to store all information tied to the websocket's session.
    """

    def __init__(self, **kwargs):
        self.session_id = kwargs.get('session_id', gen_session_id())
        self.seq = kwargs.get('seq', 0)
        self.last_seq = 0
        self.shard = kwargs.get('shard', [0, 1])
        self.user_id = kwargs.get('user_id')
        self.bot = kwargs.get('bot', False)
        self.presence = {}
        self.ws = None
        self.store = PayloadStore()

        for key in kwargs:
            value = kwargs[key]
            self.__dict__[key] = value

    def __repr__(self):
        return (f'GatewayState<seq={self.seq} '
                f'shard={self.shard} uid={self.user_id}>')
