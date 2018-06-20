import hashlib
import os


def gen_session_id() -> str:
    """Generate a random session ID."""
    return hashlib.sha1(os.urandom(256)).hexdigest()


class GatewayState:
    """Main websocket state.

    Used to store all information tied to the websocket's session.
    """

    def __init__(self, **kwargs):
        self.session_id = kwargs.get('session_id', gen_session_id())
        self.seq = kwargs.get('seq', 0)
        self.shard = kwargs.get('shard', [0, 1])
        self.user_id = kwargs.get('user_id')
        self.bot = kwargs.get('bot', False)

        for key in kwargs:
            value = kwargs[key]
            self.__dict__[key] = value

    def __repr__(self):
        return (f'GatewayState<session={self.session_id} seq={self.seq} '
                f'shard={self.shard} uid={self.user_id}>')
