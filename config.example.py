MODE = 'Development'


class Config:
    """Default configuration values for litecord."""
    DEBUG = False
    IS_SSL = False
    WEBSERVER_URL = 'localhost:5000'
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
