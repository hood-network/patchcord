MODE = 'Development'


class Config:
    """Default configuration values for litecord."""
    #: Main URL of the instance.
    MAIN_URL = 'discordapp.io'

    #: Name of the instance
    NAME = 'Litecord/Nya'

    #: Enable debug logging?
    DEBUG = False

    #: Enable ssl?
    #  many routes will start giving https / wss
    #  urls depending of this config.
    IS_SSL = False

    # enable registrations in this instance?
    REGISTRATIONS = False

    # what to give on gateway route?
    # this must point to the websocket.

    # Set this url to somewhere *your users*
    # will hit the websocket.
    # e.g 'gateway.example.com' for reverse proxies.
    WEBSOCKET_URL = 'localhost:5001'

    # Where to host the websocket?
    # (a local address the server will bind to)
    WS_HOST = '0.0.0.0'
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

    POSTGRES = {
        'host': 'some_production_postgres',
        'user': 'some_production_user',
        'password': 'some_production_password',
        'database': 'litecord_or_anything_else_really',
    }
