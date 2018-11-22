MODE = 'CI'


class Config:
    """Default configuration values for litecord."""
    MAIN_URL = 'localhost:1'
    NAME = 'gitlab ci'

    # Enable debug logging?
    DEBUG = False

    # Enable ssl? (gives wss:// instead of ws:// on gateway route)
    IS_SSL = False

    # what to give on gateway route?
    # this must point to the websocket.

    # Set this url to somewhere *your users*
    # will hit the websocket.
    # e.g 'gateway.example.com' for reverse proxies.
    WEBSOCKET_URL = 'localhost:5001'

    # Where to host the websocket?
    # (a local address the server will bind to)
    WS_HOST = 'localhost'
    WS_PORT = 5001

    # Postgres credentials
    POSTGRES = {}


class Development(Config):
    DEBUG = True
    POSTGRES = {
        'host': 'localhost',
        'user': 'litecord',
        'password': '123',
        'database': 'litecord',
    }


class Production(Config):
    DEBUG = False
    IS_SSL = True


class CI(Config):
    DEBUG = True

    POSTGRES = {
        'host': 'postgres',
        'user': 'postgres',
        'password': ''
    }
