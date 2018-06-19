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
        pass
